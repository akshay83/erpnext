# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt
from __future__ import unicode_literals

import frappe
import unittest, copy
from frappe.utils import nowdate, add_days, flt
from erpnext.stock.doctype.stock_entry.test_stock_entry import make_stock_entry, get_qty_after_transaction
from erpnext.stock.doctype.purchase_receipt.test_purchase_receipt import set_perpetual_inventory
from erpnext.exceptions import InvalidAccountCurrency, InvalidCurrency
from erpnext.stock.doctype.serial_no.serial_no import SerialNoWarehouseError
from frappe.model.naming import make_autoname

class TestSalesInvoice(unittest.TestCase):
	def make(self):
		w = frappe.copy_doc(test_records[0])
		w.is_pos = 0
		w.insert()
		w.submit()
		return w

	def test_timestamp_change(self):
		w = frappe.copy_doc(test_records[0])
		w.docstatus = 0
		w.insert()

		w2 = frappe.get_doc(w.doctype, w.name)

		import time
		time.sleep(1)
		w.save()

		import time
		time.sleep(1)
		self.assertRaises(frappe.TimestampMismatchError, w2.save)

	def test_sales_invoice_calculation_base_currency(self):
		si = frappe.copy_doc(test_records[2])
		si.insert()

		expected_values = {
			"keys": ["price_list_rate", "discount_percentage", "rate", "amount",
				"base_price_list_rate", "base_rate", "base_amount"],
			"_Test Item Home Desktop 100": [50, 0, 50, 500, 50, 50, 500],
			"_Test Item Home Desktop 200": [150, 0, 150, 750, 150, 150, 750],
		}

		# check if children are saved
		self.assertEquals(len(si.get("items")),
			len(expected_values)-1)

		# check if item values are calculated
		for d in si.get("items"):
			for i, k in enumerate(expected_values["keys"]):
				self.assertEquals(d.get(k), expected_values[d.item_code][i])

		# check net total
		self.assertEquals(si.base_net_total, 1250)
		self.assertEquals(si.net_total, 1250)

		# check tax calculation
		expected_values = {
			"keys": ["tax_amount", "total"],
			"_Test Account Shipping Charges - _TC": [100, 1350],
			"_Test Account Customs Duty - _TC": [125, 1475],
			"_Test Account Excise Duty - _TC": [140, 1615],
			"_Test Account Education Cess - _TC": [2.8, 1617.8],
			"_Test Account S&H Education Cess - _TC": [1.4, 1619.2],
			"_Test Account CST - _TC": [32.38, 1651.58],
			"_Test Account VAT - _TC": [156.25, 1807.83],
			"_Test Account Discount - _TC": [-180.78, 1627.05]
		}

		for d in si.get("taxes"):
			for i, k in enumerate(expected_values["keys"]):
				self.assertEquals(d.get(k), expected_values[d.account_head][i])

		self.assertEquals(si.base_grand_total, 1627.05)
		self.assertEquals(si.grand_total, 1627.05)

	def test_sales_invoice_calculation_export_currency(self):
		si = frappe.copy_doc(test_records[2])
		si.currency = "USD"
		si.conversion_rate = 50
		si.get("items")[0].rate = 1
		si.get("items")[0].price_list_rate = 1
		si.get("items")[1].rate = 3
		si.get("items")[1].price_list_rate = 3

		# change shipping to $2
		si.get("taxes")[0].tax_amount = 2
		si.insert()

		expected_values = {
			"keys": ["price_list_rate", "discount_percentage", "rate", "amount",
				"base_price_list_rate", "base_rate", "base_amount"],
			"_Test Item Home Desktop 100": [1, 0, 1, 10, 50, 50, 500],
			"_Test Item Home Desktop 200": [3, 0, 3, 15, 150, 150, 750],
		}

		# check if children are saved
		self.assertEquals(len(si.get("items")), len(expected_values)-1)

		# check if item values are calculated
		for d in si.get("items"):
			for i, k in enumerate(expected_values["keys"]):
				self.assertEquals(d.get(k), expected_values[d.item_code][i])

		# check net total
		self.assertEquals(si.total, 25)
		self.assertEquals(si.base_total, 1250)
		self.assertEquals(si.net_total, 25)
		self.assertEquals(si.base_net_total, 1250)

		# check tax calculation
		expected_values = {
			"keys": ["base_tax_amount", "base_total", "tax_amount", "total"],
			"_Test Account Shipping Charges - _TC": [100, 1350, 2, 27],
			"_Test Account Customs Duty - _TC": [125, 1475, 2.5, 29.5],
			"_Test Account Excise Duty - _TC": [140, 1615, 2.8, 32.3],
			"_Test Account Education Cess - _TC": [3, 1618, 0.06, 32.36],
			"_Test Account S&H Education Cess - _TC": [1.5, 1619.5, 0.03, 32.39],
			"_Test Account CST - _TC": [32.5, 1652, 0.65, 33.04],
			"_Test Account VAT - _TC": [156.5, 1808.5, 3.13, 36.17],
			"_Test Account Discount - _TC": [-180.5, 1628, -3.61, 32.56]
		}

		for d in si.get("taxes"):
			for i, k in enumerate(expected_values["keys"]):
				self.assertEquals(d.get(k), expected_values[d.account_head][i])

		self.assertEquals(si.base_grand_total, 1628)
		self.assertEquals(si.grand_total, 32.56)

	def test_sales_invoice_discount_amount(self):
		si = frappe.copy_doc(test_records[3])
		si.discount_amount = 104.95
		si.append("taxes", {
			"doctype": "Sales Taxes and Charges",
			"charge_type": "On Previous Row Amount",
			"account_head": "_Test Account Service Tax - _TC",
			"cost_center": "_Test Cost Center - _TC",
			"description": "Service Tax",
			"rate": 10,
			"row_id": 8,
		})
		si.insert()

		expected_values = [
			{
				"item_code": "_Test Item Home Desktop 100",
				"price_list_rate": 62.5,
				"discount_percentage": 0,
				"rate": 62.5, "amount": 625,
				"base_price_list_rate": 62.5,
				"base_rate": 62.5, "base_amount": 625,
				"net_rate": 46.54, "net_amount": 465.37,
				"base_net_rate": 46.54, "base_net_amount": 465.37
			},
			{
				"item_code": "_Test Item Home Desktop 200",
				"price_list_rate": 190.66,
				"discount_percentage": 0,
				"rate": 190.66, "amount": 953.3,
				"base_price_list_rate": 190.66,
				"base_rate": 190.66, "base_amount": 953.3,
				"net_rate": 139.62, "net_amount": 698.08,
				"base_net_rate": 139.62, "base_net_amount": 698.08
			}
		]

		# check if children are saved
		self.assertEquals(len(si.get("items")),	len(expected_values))

		# check if item values are calculated
		for i, d in enumerate(si.get("items")):
			for k, v in expected_values[i].items():
				self.assertEquals(d.get(k), v)

		# check net total
		self.assertEquals(si.base_net_total, 1163.45)
		self.assertEquals(si.total, 1578.3)

		# check tax calculation
		expected_values = {
			"keys": ["tax_amount", "tax_amount_after_discount_amount", "total"],
			"_Test Account Excise Duty - _TC": [140, 130.31, 1293.76],
			"_Test Account Education Cess - _TC": [2.8, 2.61, 1296.37],
			"_Test Account S&H Education Cess - _TC": [1.4, 1.31, 1297.68],
			"_Test Account CST - _TC": [27.88, 25.96, 1323.64],
			"_Test Account VAT - _TC": [156.25, 145.43, 1469.07],
			"_Test Account Customs Duty - _TC": [125, 116.35, 1585.42],
			"_Test Account Shipping Charges - _TC": [100, 100, 1685.42],
			"_Test Account Discount - _TC": [-180.33, -168.54, 1516.88],
			"_Test Account Service Tax - _TC": [-18.03, -16.88, 1500]
		}

		for d in si.get("taxes"):
			for i, k in enumerate(expected_values["keys"]):
				self.assertEquals(d.get(k), expected_values[d.account_head][i])

		self.assertEquals(si.base_grand_total, 1500)
		self.assertEquals(si.grand_total, 1500)

	def test_discount_amount_gl_entry(self):
		si = frappe.copy_doc(test_records[3])
		si.discount_amount = 104.95
		si.append("taxes", {
			"doctype": "Sales Taxes and Charges",
			"charge_type": "On Previous Row Amount",
			"account_head": "_Test Account Service Tax - _TC",
			"cost_center": "_Test Cost Center - _TC",
			"description": "Service Tax",
			"rate": 10,
			"row_id": 8
		})
		si.insert()
		si.submit()

		gl_entries = frappe.db.sql("""select account, debit, credit
			from `tabGL Entry` where voucher_type='Sales Invoice' and voucher_no=%s
			order by account asc""", si.name, as_dict=1)

		self.assertTrue(gl_entries)

		expected_values = dict((d[0], d) for d in [
			[si.debit_to, 1500, 0.0],
			[test_records[3]["items"][0]["income_account"], 0.0, 1163.45],
			[test_records[3]["taxes"][0]["account_head"], 0.0, 130.31],
			[test_records[3]["taxes"][1]["account_head"], 0.0, 2.61],
			[test_records[3]["taxes"][2]["account_head"], 0.0, 1.31],
			[test_records[3]["taxes"][3]["account_head"], 0.0, 25.96],
			[test_records[3]["taxes"][4]["account_head"], 0.0, 145.43],
			[test_records[3]["taxes"][5]["account_head"], 0.0, 116.35],
			[test_records[3]["taxes"][6]["account_head"], 0.0, 100],
			[test_records[3]["taxes"][7]["account_head"], 168.54, 0.0],
			["_Test Account Service Tax - _TC", 16.88, 0.0],
		])

		for gle in gl_entries:
			self.assertEquals(expected_values[gle.account][0], gle.account)
			self.assertEquals(expected_values[gle.account][1], gle.debit)
			self.assertEquals(expected_values[gle.account][2], gle.credit)

		# cancel
		si.cancel()

		gle = frappe.db.sql("""select * from `tabGL Entry`
			where voucher_type='Sales Invoice' and voucher_no=%s""", si.name)

		self.assertFalse(gle)

	def test_inclusive_rate_validations(self):
		si = frappe.copy_doc(test_records[2])
		for i, tax in enumerate(si.get("taxes")):
			tax.idx = i+1

		si.get("items")[0].price_list_rate = 62.5
		si.get("items")[0].price_list_rate = 191
		for i in xrange(6):
			si.get("taxes")[i].included_in_print_rate = 1

		# tax type "Actual" cannot be inclusive
		self.assertRaises(frappe.ValidationError, si.insert)

		# taxes above included type 'On Previous Row Total' should also be included
		si.get("taxes")[0].included_in_print_rate = 0
		self.assertRaises(frappe.ValidationError, si.insert)

	def test_sales_invoice_calculation_base_currency_with_tax_inclusive_price(self):
		# prepare
		si = frappe.copy_doc(test_records[3])
		si.insert()

		expected_values = {
			"keys": ["price_list_rate", "discount_percentage", "rate", "amount",
				"base_price_list_rate", "base_rate", "base_amount", "net_rate", "net_amount"],
			"_Test Item Home Desktop 100": [62.5, 0, 62.5, 625.0, 62.5, 62.5, 625.0, 50, 499.98],
			"_Test Item Home Desktop 200": [190.66, 0, 190.66, 953.3, 190.66, 190.66, 953.3, 150, 750],
		}

		# check if children are saved
		self.assertEquals(len(si.get("items")),
			len(expected_values)-1)

		# check if item values are calculated
		for d in si.get("items"):
			for i, k in enumerate(expected_values["keys"]):
				self.assertEquals(d.get(k), expected_values[d.item_code][i])

		# check net total
		self.assertEquals(si.base_net_total, 1249.98)
		self.assertEquals(si.total, 1578.3)

		# check tax calculation
		expected_values = {
			"keys": ["tax_amount", "total"],
			"_Test Account Excise Duty - _TC": [140, 1389.98],
			"_Test Account Education Cess - _TC": [2.8, 1392.78],
			"_Test Account S&H Education Cess - _TC": [1.4, 1394.18],
			"_Test Account CST - _TC": [27.88, 1422.06],
			"_Test Account VAT - _TC": [156.25, 1578.31],
			"_Test Account Customs Duty - _TC": [125, 1703.31],
			"_Test Account Shipping Charges - _TC": [100, 1803.31],
			"_Test Account Discount - _TC": [-180.33, 1622.98]
		}

		for d in si.get("taxes"):
			for i, k in enumerate(expected_values["keys"]):
				self.assertEquals(d.get(k), expected_values[d.account_head][i])

		self.assertEquals(si.base_grand_total, 1622.98)
		self.assertEquals(si.grand_total, 1622.98)

	def test_sales_invoice_calculation_export_currency_with_tax_inclusive_price(self):
		# prepare
		si = frappe.copy_doc(test_records[3])
		si.currency = "USD"
		si.conversion_rate = 50
		si.get("items")[0].price_list_rate = 55.56
		si.get("items")[0].discount_percentage = 10
		si.get("items")[1].price_list_rate = 187.5
		si.get("items")[1].discount_percentage = 20

		# change shipping to $2
		si.get("taxes")[6].tax_amount = 2

		si.insert()

		expected_values = [
			{
				"item_code": "_Test Item Home Desktop 100",
				"price_list_rate": 55.56,
				"discount_percentage": 10,
				"rate": 50, "amount": 500,
				"base_price_list_rate": 2778,
				"base_rate": 2500, "base_amount": 25000,
				"net_rate": 40, "net_amount": 399.98,
				"base_net_rate": 2000, "base_net_amount": 19999
			},
			{
				"item_code": "_Test Item Home Desktop 200",
				"price_list_rate": 187.5,
				"discount_percentage": 20,
				"rate": 150, "amount": 750,
				"base_price_list_rate": 9375,
				"base_rate": 7500, "base_amount": 37500,
				"net_rate": 118.01, "net_amount": 590.05,
				"base_net_rate": 5900.5, "base_net_amount": 29502.5
			}
		]

		# check if children are saved
		self.assertEquals(len(si.get("items")), len(expected_values))

		# check if item values are calculated
		for i, d in enumerate(si.get("items")):
			for key, val in expected_values[i].items():
				self.assertEquals(d.get(key), val)

		# check net total
		self.assertEquals(si.base_net_total, 49501.5)
		self.assertEquals(si.net_total, 990.03)
		self.assertEquals(si.total, 1250)

		# check tax calculation
		expected_values = {
			"keys": ["base_tax_amount", "base_total", "tax_amount", "total"],
			"_Test Account Excise Duty - _TC": [5540.5, 55042, 110.81, 1100.84],
			"_Test Account Education Cess - _TC": [111, 55153, 2.22, 1103.06],
			"_Test Account S&H Education Cess - _TC": [55.5, 55208.5, 1.11, 1104.17],
			"_Test Account CST - _TC": [1104, 56312.5, 22.08, 1126.25],
			"_Test Account VAT - _TC": [6188, 62500.5, 123.76, 1250.01],
			"_Test Account Customs Duty - _TC": [4950.5, 67451, 99.01, 1349.02],
			"_Test Account Shipping Charges - _TC": [ 100, 67551, 2, 1351.02],
			"_Test Account Discount - _TC": [ -6755, 60796, -135.10, 1215.92]
		}

		for d in si.get("taxes"):
			for i, k in enumerate(expected_values["keys"]):
				self.assertEquals(d.get(k), expected_values[d.account_head][i])

		self.assertEquals(si.base_grand_total, 60796)
		self.assertEquals(si.grand_total, 1215.92)

	def test_outstanding(self):
		w = self.make()
		self.assertEquals(w.outstanding_amount, w.base_grand_total)

	def test_payment(self):
		w = self.make()

		from erpnext.accounts.doctype.journal_entry.test_journal_entry \
			import test_records as jv_test_records

		jv = frappe.get_doc(frappe.copy_doc(jv_test_records[0]))
		jv.get("accounts")[0].reference_type = w.doctype
		jv.get("accounts")[0].reference_name = w.name
		jv.insert()
		jv.submit()

		self.assertEquals(frappe.db.get_value("Sales Invoice", w.name, "outstanding_amount"), 161.8)

		jv.cancel()
		self.assertEquals(frappe.db.get_value("Sales Invoice", w.name, "outstanding_amount"), 561.8)

	def test_sales_invoice_gl_entry_without_perpetual_inventory(self):
		set_perpetual_inventory(0)
		si = frappe.copy_doc(test_records[1])
		si.insert()
		si.submit()

		gl_entries = frappe.db.sql("""select account, debit, credit
			from `tabGL Entry` where voucher_type='Sales Invoice' and voucher_no=%s
			order by account asc""", si.name, as_dict=1)

		self.assertTrue(gl_entries)

		expected_values = dict((d[0], d) for d in [
			[si.debit_to, 630.0, 0.0],
			[test_records[1]["items"][0]["income_account"], 0.0, 500.0],
			[test_records[1]["taxes"][0]["account_head"], 0.0, 80.0],
			[test_records[1]["taxes"][1]["account_head"], 0.0, 50.0],
		])

		for i, gle in enumerate(gl_entries):
			self.assertEquals(expected_values[gle.account][0], gle.account)
			self.assertEquals(expected_values[gle.account][1], gle.debit)
			self.assertEquals(expected_values[gle.account][2], gle.credit)

		# cancel
		si.cancel()

		gle = frappe.db.sql("""select * from `tabGL Entry`
			where voucher_type='Sales Invoice' and voucher_no=%s""", si.name)

		self.assertFalse(gle)

	def test_pos_gl_entry_with_perpetual_inventory(self):
		set_perpetual_inventory()
		self.make_pos_profile()

		self._insert_purchase_receipt()
		pos = copy.deepcopy(test_records[1])
		pos["is_pos"] = 1
		pos["update_stock"] = 1
		pos["payments"] = [{'mode_of_payment': 'Bank Draft', 'account': '_Test Bank - _TC', 'amount': 300},
							{'mode_of_payment': 'Cash', 'account': 'Cash - _TC', 'amount': 300}]

		si = frappe.copy_doc(pos)
		si.insert()
		si.submit()

		self.assertEquals(si.paid_amount, 600.0)

		self.pos_gl_entry(si, pos, 300)

	def test_make_pos_invoice(self):
		from erpnext.accounts.doctype.sales_invoice.pos import make_invoice

		set_perpetual_inventory()

		self.make_pos_profile()
		self._insert_purchase_receipt()

		pos = copy.deepcopy(test_records[1])
		pos["is_pos"] = 1
		pos["update_stock"] = 1
		pos["payments"] = [{'mode_of_payment': 'Bank Draft', 'account': '_Test Bank - _TC', 'amount': 300},
							{'mode_of_payment': 'Cash', 'account': 'Cash - _TC', 'amount': 330}]

		invoice_data = [{'09052016142': pos}]
		si = make_invoice(invoice_data)
		self.assertEquals(si[0], '09052016142')

		sales_invoice = frappe.get_all('Sales Invoice', fields =["*"], filters = {'offline_pos_name': '09052016142', 'docstatus': 1})
		si = frappe.get_doc('Sales Invoice', sales_invoice[0].name)
		self.assertEquals(si.grand_total, 630.0)

		self.pos_gl_entry(si, pos, 330)

	def pos_gl_entry(self, si, pos, cash_amount):
		# check stock ledger entries
		sle = frappe.db.sql("""select * from `tabStock Ledger Entry`
			where voucher_type = 'Sales Invoice' and voucher_no = %s""",
			si.name, as_dict=1)[0]
		self.assertTrue(sle)
		self.assertEquals([sle.item_code, sle.warehouse, sle.actual_qty],
			["_Test Item", "_Test Warehouse - _TC", -1.0])

		# check gl entries
		gl_entries = frappe.db.sql("""select account, debit, credit
			from `tabGL Entry` where voucher_type='Sales Invoice' and voucher_no=%s
			order by account asc, debit asc""", si.name, as_dict=1)
		self.assertTrue(gl_entries)

		stock_in_hand = frappe.db.get_value("Account", {"warehouse": "_Test Warehouse - _TC"})

		expected_gl_entries = sorted([
			[si.debit_to, 630.0, 0.0],
			[pos["items"][0]["income_account"], 0.0, 500.0],
			[pos["taxes"][0]["account_head"], 0.0, 80.0],
			[pos["taxes"][1]["account_head"], 0.0, 50.0],
			[stock_in_hand, 0.0, abs(sle.stock_value_difference)],
			[pos["items"][0]["expense_account"], abs(sle.stock_value_difference), 0.0],
			[si.debit_to, 0.0, si.paid_amount],
			["_Test Bank - _TC", 300.0, 0.0],
			["Cash - _TC", cash_amount, 0.0]
		])

		for i, gle in enumerate(sorted(gl_entries, key=lambda gle: gle.account)):
			self.assertEquals(expected_gl_entries[i][0], gle.account)
			self.assertEquals(expected_gl_entries[i][1], gle.debit)
			self.assertEquals(expected_gl_entries[i][2], gle.credit)

		si.cancel()
		gle = frappe.db.sql("""select * from `tabGL Entry`
			where voucher_type='Sales Invoice' and voucher_no=%s""", si.name)

		self.assertFalse(gle)

		set_perpetual_inventory(0)

		frappe.db.sql("delete from `tabPOS Profile`")

	def make_pos_profile(self):
		pos_profile = frappe.get_doc({
			"company": "_Test Company",
			"cost_center": "_Test Cost Center - _TC",
			"currency": "INR",
			"doctype": "POS Profile",
			"expense_account": "_Test Account Cost for Goods Sold - _TC",
			"income_account": "Sales - _TC",
			"name": "_Test POS Profile",
			"naming_series": "_T-POS Profile-",
			"selling_price_list": "_Test Price List",
			"territory": "_Test Territory",
			"warehouse": "_Test Warehouse - _TC",
			"write_off_account": "_Test Write Off - _TC",
			"write_off_cost_center": "_Test Write Off Cost Center - _TC"
		})

		if not frappe.db.exists("POS Profile", "_Test POS Profile"):
			pos_profile.insert()

	def test_si_gl_entry_with_perpetual_inventory_and_update_stock_with_warehouse_but_no_account(self):
		set_perpetual_inventory()
		frappe.delete_doc("Account", "_Test Warehouse No Account - _TC")

		# insert purchase receipt
		from erpnext.stock.doctype.purchase_receipt.test_purchase_receipt import test_records \
			as pr_test_records
		pr = frappe.copy_doc(pr_test_records[0])
		pr.naming_series = "_T-Purchase Receipt-"
		pr.get("items")[0].warehouse = "_Test Warehouse No Account - _TC"
		pr.insert()
		pr.submit()

		si_doc = copy.deepcopy(test_records[1])
		si_doc["update_stock"] = 1
		# si_doc["posting_time"] = "12:05"
		si_doc.get("items")[0]["warehouse"] = "_Test Warehouse No Account - _TC"

		si = frappe.copy_doc(si_doc)
		si.insert()
		si.submit()

		# check stock ledger entries
		sle = frappe.db.sql("""select * from `tabStock Ledger Entry`
			where voucher_type = 'Sales Invoice' and voucher_no = %s""",
			si.name, as_dict=1)[0]
		self.assertTrue(sle)
		self.assertEquals([sle.item_code, sle.warehouse, sle.actual_qty],
			["_Test Item", "_Test Warehouse No Account - _TC", -1.0])

		# check gl entries
		gl_entries = frappe.db.sql("""select account, debit, credit
			from `tabGL Entry` where voucher_type='Sales Invoice' and voucher_no=%s
			order by account asc, debit asc""", si.name, as_dict=1)
		self.assertTrue(gl_entries)

		expected_gl_entries = dict((d[0], d) for d in [
			[si.debit_to, 630.0, 0.0],
			[si_doc.get("items")[0]["income_account"], 0.0, 500.0],
			[si_doc.get("taxes")[0]["account_head"], 0.0, 80.0],
			[si_doc.get("taxes")[1]["account_head"], 0.0, 50.0],
		])
		for i, gle in enumerate(gl_entries):
			self.assertEquals(expected_gl_entries[gle.account][0], gle.account)
			self.assertEquals(expected_gl_entries[gle.account][1], gle.debit)
			self.assertEquals(expected_gl_entries[gle.account][2], gle.credit)

		si.cancel()
		gle = frappe.db.sql("""select * from `tabGL Entry`
			where voucher_type='Sales Invoice' and voucher_no=%s""", si.name)

		self.assertFalse(gle)
		set_perpetual_inventory(0)

	def test_sales_invoice_gl_entry_with_perpetual_inventory_no_item_code(self):
		set_perpetual_inventory()

		si = frappe.get_doc(test_records[1])
		si.get("items")[0].item_code = None
		si.insert()
		si.submit()

		gl_entries = frappe.db.sql("""select account, debit, credit
			from `tabGL Entry` where voucher_type='Sales Invoice' and voucher_no=%s
			order by account asc""", si.name, as_dict=1)
		self.assertTrue(gl_entries)

		expected_values = dict((d[0], d) for d in [
			[si.debit_to, 630.0, 0.0],
			[test_records[1]["items"][0]["income_account"], 0.0, 500.0],
			[test_records[1]["taxes"][0]["account_head"], 0.0, 80.0],
			[test_records[1]["taxes"][1]["account_head"], 0.0, 50.0],
		])
		for i, gle in enumerate(gl_entries):
			self.assertEquals(expected_values[gle.account][0], gle.account)
			self.assertEquals(expected_values[gle.account][1], gle.debit)
			self.assertEquals(expected_values[gle.account][2], gle.credit)

		set_perpetual_inventory(0)

	def test_sales_invoice_gl_entry_with_perpetual_inventory_non_stock_item(self):
		set_perpetual_inventory()
		si = frappe.get_doc(test_records[1])
		si.get("items")[0].item_code = "_Test Non Stock Item"
		si.insert()
		si.submit()

		gl_entries = frappe.db.sql("""select account, debit, credit
			from `tabGL Entry` where voucher_type='Sales Invoice' and voucher_no=%s
			order by account asc""", si.name, as_dict=1)
		self.assertTrue(gl_entries)

		expected_values = dict((d[0], d) for d in [
			[si.debit_to, 630.0, 0.0],
			[test_records[1]["items"][0]["income_account"], 0.0, 500.0],
			[test_records[1]["taxes"][0]["account_head"], 0.0, 80.0],
			[test_records[1]["taxes"][1]["account_head"], 0.0, 50.0],
		])
		for i, gle in enumerate(gl_entries):
			self.assertEquals(expected_values[gle.account][0], gle.account)
			self.assertEquals(expected_values[gle.account][1], gle.debit)
			self.assertEquals(expected_values[gle.account][2], gle.credit)

		set_perpetual_inventory(0)

	def _insert_purchase_receipt(self):
		from erpnext.stock.doctype.purchase_receipt.test_purchase_receipt import test_records \
			as pr_test_records
		pr = frappe.copy_doc(pr_test_records[0])
		pr.naming_series = "_T-Purchase Receipt-"
		pr.insert()
		pr.submit()

	def _insert_delivery_note(self):
		from erpnext.stock.doctype.delivery_note.test_delivery_note import test_records \
			as dn_test_records
		dn = frappe.copy_doc(dn_test_records[0])
		dn.naming_series = "_T-Delivery Note-"
		dn.insert()
		dn.submit()
		return dn

	def test_sales_invoice_with_advance(self):
		from erpnext.accounts.doctype.journal_entry.test_journal_entry \
			import test_records as jv_test_records

		jv = frappe.copy_doc(jv_test_records[0])
		jv.insert()
		jv.submit()

		si = frappe.copy_doc(test_records[0])
		si.append("advances", {
			"doctype": "Sales Invoice Advance",
			"reference_type": "Journal Entry",
			"reference_name": jv.name,
			"reference_row": jv.get("accounts")[0].name,
			"advance_amount": 400,
			"allocated_amount": 300,
			"remarks": jv.remark
		})
		si.insert()
		si.submit()
		si.load_from_db()

		self.assertTrue(frappe.db.sql("""select name from `tabJournal Entry Account`
			where reference_name=%s""", si.name))

		self.assertTrue(frappe.db.sql("""select name from `tabJournal Entry Account`
			where reference_name=%s and credit_in_account_currency=300""", si.name))

		self.assertEqual(si.outstanding_amount, 261.8)

		si.cancel()

		self.assertTrue(not frappe.db.sql("""select name from `tabJournal Entry Account`
			where reference_name=%s""", si.name))

	def test_recurring_invoice(self):
		from erpnext.controllers.tests.test_recurring_document import test_recurring_document
		test_recurring_document(self, test_records)

	def test_serialized(self):
		from erpnext.stock.doctype.stock_entry.test_stock_entry import make_serialized_item
		from erpnext.stock.doctype.serial_no.serial_no import get_serial_nos

		se = make_serialized_item()
		serial_nos = get_serial_nos(se.get("items")[0].serial_no)

		si = frappe.copy_doc(test_records[0])
		si.update_stock = 1
		si.get("items")[0].item_code = "_Test Serialized Item With Series"
		si.get("items")[0].qty = 1
		si.get("items")[0].serial_no = serial_nos[0]
		si.insert()
		si.submit()

		self.assertFalse(frappe.db.get_value("Serial No", serial_nos[0], "warehouse"))
		self.assertEquals(frappe.db.get_value("Serial No", serial_nos[0],
			"delivery_document_no"), si.name)

		return si

	def test_serialized_cancel(self):
		from erpnext.stock.doctype.serial_no.serial_no import get_serial_nos
		si = self.test_serialized()
		si.cancel()

		serial_nos = get_serial_nos(si.get("items")[0].serial_no)

		self.assertEquals(frappe.db.get_value("Serial No", serial_nos[0], "warehouse"), "_Test Warehouse - _TC")
		self.assertFalse(frappe.db.get_value("Serial No", serial_nos[0],
			"delivery_document_no"))

	def test_serialize_status(self):
		serial_no = frappe.get_doc({
			"doctype": "Serial No",
			"item_code": "_Test Serialized Item With Series",
			"serial_no": make_autoname("SR", "Serial No")
		})
		serial_no.save()

		si = frappe.copy_doc(test_records[0])
		si.update_stock = 1
		si.get("items")[0].item_code = "_Test Serialized Item With Series"
		si.get("items")[0].qty = 1
		si.get("items")[0].serial_no = serial_no.name
		si.insert()

		self.assertRaises(SerialNoWarehouseError, si.submit)

	def test_invoice_due_date_against_customers_credit_days(self):
		# set customer's credit days
		frappe.db.set_value("Customer", "_Test Customer", "credit_days_based_on", "Fixed Days")
		frappe.db.set_value("Customer", "_Test Customer", "credit_days", 10)

		si = create_sales_invoice()
		self.assertEqual(si.due_date, add_days(nowdate(), 10))

		# set customer's credit days is last day of the next month
		frappe.db.set_value("Customer", "_Test Customer", "credit_days_based_on", "Last Day of the Next Month")

		si1 = create_sales_invoice(posting_date="2015-07-05")
		self.assertEqual(si1.due_date, "2015-08-31")

	def test_return_sales_invoice(self):
		set_perpetual_inventory()
		make_stock_entry(item_code="_Test Item", target="_Test Warehouse - _TC", qty=50, basic_rate=100)

		actual_qty_0 = get_qty_after_transaction()

		si = create_sales_invoice(qty=5, rate=500, update_stock=1)

		actual_qty_1 = get_qty_after_transaction()
		self.assertEquals(actual_qty_0 - 5, actual_qty_1)

		# outgoing_rate
		outgoing_rate = frappe.db.get_value("Stock Ledger Entry", {"voucher_type": "Sales Invoice",
			"voucher_no": si.name}, "stock_value_difference") / 5

		# return entry
		si1 = create_sales_invoice(is_return=1, return_against=si.name, qty=-2, rate=500, update_stock=1)

		actual_qty_2 = get_qty_after_transaction()

		self.assertEquals(actual_qty_1 + 2, actual_qty_2)

		incoming_rate, stock_value_difference = frappe.db.get_value("Stock Ledger Entry",
			{"voucher_type": "Sales Invoice", "voucher_no": si1.name},
			["incoming_rate", "stock_value_difference"])

		self.assertEquals(flt(incoming_rate, 3), abs(flt(outgoing_rate, 3)))


		# Check gl entry
		gle_warehouse_amount = frappe.db.get_value("GL Entry", {"voucher_type": "Sales Invoice",
			"voucher_no": si1.name, "account": "_Test Warehouse - _TC"}, "debit")

		self.assertEquals(gle_warehouse_amount, stock_value_difference)

		party_credited = frappe.db.get_value("GL Entry", {"voucher_type": "Sales Invoice",
			"voucher_no": si1.name, "account": "Debtors - _TC", "party": "_Test Customer"}, "credit")

		self.assertEqual(party_credited, 1000)

		# Check outstanding amount
		self.assertFalse(si1.outstanding_amount)
		self.assertEqual(frappe.db.get_value("Sales Invoice", si.name, "outstanding_amount"), 1500)

		set_perpetual_inventory(0)

	def test_discount_on_net_total(self):
		si = frappe.copy_doc(test_records[2])
		si.apply_discount_on = "Net Total"
		si.discount_amount = 625
		si.insert()

		expected_values = {
			"keys": ["price_list_rate", "discount_percentage", "rate", "amount",
				"base_price_list_rate", "base_rate", "base_amount",
				"net_rate", "base_net_rate", "net_amount", "base_net_amount"],
			"_Test Item Home Desktop 100": [50, 0, 50, 500, 50, 50, 500, 25, 25, 250, 250],
			"_Test Item Home Desktop 200": [150, 0, 150, 750, 150, 150, 750, 75, 75, 375, 375],
		}

		# check if children are saved
		self.assertEquals(len(si.get("items")),
			len(expected_values)-1)

		# check if item values are calculated
		for d in si.get("items"):
			for i, k in enumerate(expected_values["keys"]):
				self.assertEquals(d.get(k), expected_values[d.item_code][i])

		# check net total
		self.assertEquals(si.base_total, 1250)
		self.assertEquals(si.total, 1250)
		self.assertEquals(si.base_net_total, 625)
		self.assertEquals(si.net_total, 625)

		# check tax calculation
		expected_values = {
			"keys": ["tax_amount", "tax_amount_after_discount_amount",
				"base_tax_amount_after_discount_amount"],
			"_Test Account Shipping Charges - _TC": [100, 100, 100],
			"_Test Account Customs Duty - _TC": [62.5, 62.5, 62.5],
			"_Test Account Excise Duty - _TC": [70, 70, 70],
			"_Test Account Education Cess - _TC": [1.4, 1.4, 1.4],
			"_Test Account S&H Education Cess - _TC": [.7, 0.7, 0.7],
			"_Test Account CST - _TC": [17.2, 17.2, 17.2],
			"_Test Account VAT - _TC": [78.13, 78.13, 78.13],
			"_Test Account Discount - _TC": [-95.49, -95.49, -95.49]
		}

		for d in si.get("taxes"):
			for i, k in enumerate(expected_values["keys"]):
				self.assertEquals(d.get(k), expected_values[d.account_head][i])


		self.assertEquals(si.total_taxes_and_charges, 234.44)
		self.assertEquals(si.base_grand_total, 859.44)
		self.assertEquals(si.grand_total, 859.44)

	def test_multi_currency_gle(self):
		set_perpetual_inventory(0)
		si = create_sales_invoice(customer="_Test Customer USD", debit_to="_Test Receivable USD - _TC",
			currency="USD", conversion_rate=50)

		gl_entries = frappe.db.sql("""select account, account_currency, debit, credit,
			debit_in_account_currency, credit_in_account_currency
			from `tabGL Entry` where voucher_type='Sales Invoice' and voucher_no=%s
			order by account asc""", si.name, as_dict=1)

		self.assertTrue(gl_entries)

		expected_values = {
			"_Test Receivable USD - _TC": {
				"account_currency": "USD",
				"debit": 5000,
				"debit_in_account_currency": 100,
				"credit": 0,
				"credit_in_account_currency": 0
			},
			"Sales - _TC": {
				"account_currency": "INR",
				"debit": 0,
				"debit_in_account_currency": 0,
				"credit": 5000,
				"credit_in_account_currency": 5000
			}
		}

		for field in ("account_currency", "debit", "debit_in_account_currency", "credit", "credit_in_account_currency"):
			for i, gle in enumerate(gl_entries):
				self.assertEquals(expected_values[gle.account][field], gle[field])

		# cancel
		si.cancel()

		gle = frappe.db.sql("""select name from `tabGL Entry`
			where voucher_type='Sales Invoice' and voucher_no=%s""", si.name)

		self.assertFalse(gle)

	def test_invalid_currency(self):
		# Customer currency = USD

		# Transaction currency cannot be INR
		si1 = create_sales_invoice(customer="_Test Customer USD", debit_to="_Test Receivable USD - _TC",
			do_not_save=True)

		self.assertRaises(InvalidCurrency, si1.save)

		# Transaction currency cannot be EUR
		si2 = create_sales_invoice(customer="_Test Customer USD", debit_to="_Test Receivable USD - _TC",
			currency="EUR", conversion_rate=80, do_not_save=True)

		self.assertRaises(InvalidCurrency, si2.save)

		# Transaction currency only allowed in USD
		si3 = create_sales_invoice(customer="_Test Customer USD", debit_to="_Test Receivable USD - _TC",
			currency="USD", conversion_rate=50)

		# Party Account currency must be in USD, as there is existing GLE with USD
		si4 = create_sales_invoice(customer="_Test Customer USD", debit_to="_Test Receivable - _TC",
			currency="USD", conversion_rate=50, do_not_submit=True)

		self.assertRaises(InvalidAccountCurrency, si4.submit)

		# Party Account currency must be in USD, force customer currency as there is no GLE

		si3.cancel()
		si5 = create_sales_invoice(customer="_Test Customer USD", debit_to="_Test Receivable - _TC",
			currency="USD", conversion_rate=50, do_not_submit=True)

		self.assertRaises(InvalidAccountCurrency, si5.submit)

	def test_create_so_with_margin(self):
		si = create_sales_invoice(item_code="_Test Item", qty=1, do_not_submit=True)
		price_list_rate = si.items[0].price_list_rate
		si.items[0].margin_type = 'Percentage'
		si.items[0].margin_rate_or_amount = 25
		si.insert()

		self.assertNotEquals(si.get("items")[0].rate, flt((price_list_rate*25)/100 + price_list_rate))
		si.items[0].margin_rate_or_amount = 25
		si.submit()

		self.assertNotEquals(si.get("items")[0].rate, flt((price_list_rate*25)/100 + price_list_rate))

	def test_party_status(self):
		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
		from frappe.utils import random_string

		customer_name = 'test customer for status'

		if frappe.db.exists('Customer', customer_name):
			customer = frappe.get_doc('Customer', customer_name)
			customer.db_set('status', 'Active')
		else:
			customer = frappe.get_doc({
				'doctype': 'Customer',
				'customer_name': customer_name,
				'customer_group': 'Commercial',
				'customer_type': 'Individual',
				'territory': 'Rest of the World'
			}).insert()

		self.assertEquals(frappe.db.get_value('Customer', customer.name, 'status'), 'Active')

		invoice = create_sales_invoice(customer="test customer for status",
			debit_to="_Test Receivable - _TC",
			currency="USD", conversion_rate=50)

		self.assertEquals(frappe.db.get_value('Customer', customer.name, 'status'), 'Open')

		pe = get_payment_entry(invoice.doctype, invoice.name)
		pe.reference_no = random_string(10)
		pe.reference_date = invoice.posting_date
		pe.insert()
		pe.submit()

		self.assertEquals(frappe.db.get_value('Customer', customer.name, 'status'), 'Active')

def create_sales_invoice(**args):
	si = frappe.new_doc("Sales Invoice")
	args = frappe._dict(args)
	si.posting_date = args.posting_date or nowdate()

	si.company = args.company or "_Test Company"
	si.customer = args.customer or "_Test Customer"
	si.debit_to = args.debit_to or "Debtors - _TC"
	si.update_stock = args.update_stock
	si.is_pos = args.is_pos
	si.is_return = args.is_return
	si.return_against = args.return_against
	si.currency=args.currency or "INR"
	si.conversion_rate = args.conversion_rate or 1

	si.append("items", {
		"item_code": args.item or args.item_code or "_Test Item",
		"warehouse": args.warehouse or "_Test Warehouse - _TC",
		"qty": args.qty or 1,
		"rate": args.rate or 100,
		"income_account": "Sales - _TC",
		"expense_account": "Cost of Goods Sold - _TC",
		"cost_center": "_Test Cost Center - _TC",
		"serial_no": args.serial_no
	})

	if not args.do_not_save:
		si.insert()
		if not args.do_not_submit:
			si.submit()
	return si

test_dependencies = ["Journal Entry", "Contact", "Address"]
test_records = frappe.get_test_records('Sales Invoice')
