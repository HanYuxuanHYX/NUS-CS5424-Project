import decimal
from datetime import datetime
from create_tables import *
from cassandra import ConsistencyLevel

READ_CONSISTENCY = ConsistencyLevel.ONE
WRITE_CONSISTENCY = ConsistencyLevel.ALL


def new_order_transaction(w_id, d_id, c_id, num_items, item_num, supplier_warehouse, quantity):
    warehouse = Warehouse.filter(W_ID=w_id).consistency(READ_CONSISTENCY).get()
    district = District.filter(D_W_ID=w_id, D_ID=d_id).consistency(WRITE_CONSISTENCY).get()
    customer = Customer.filter(C_W_ID=w_id, C_D_ID=d_id, C_ID=c_id).consistency(READ_CONSISTENCY).get()

    # Processing steps

    n = district.D_NEXT_O_ID
    district.update(D_NEXT_O_ID=n + 1)
    entry_time = datetime.utcnow()
    local = all([w_id == i for i in supplier_warehouse])
    Order.create(O_ID=n, O_D_ID=d_id, O_W_ID=w_id, O_C_ID=c_id, O_ENTRY_D=entry_time,
                 O_OL_CNT=num_items, O_ALL_LOCAL=local)

    total_amount = 0
    for i in range(num_items):
        item = Item.filter(I_ID=item_num[i]).consistency(READ_CONSISTENCY).get()
        stock = Stock.filter(S_W_ID=w_id, S_I_ID=item_num[i]).consistency(WRITE_CONSISTENCY).get()
        adjusted_qty = stock.S_QUANTITY - quantity[i]
        if adjusted_qty < 10:
            adjusted_qty += 100
        stock.update(S_QUANTITY=adjusted_qty, S_YTD=stock.S_YTD + quantity[i], S_ORDER_CNT=stock.S_ORDER_CNT + 1)
        if supplier_warehouse[i] != w_id:
            stock.update(S_REMOTE_CNT=stock.S_REMOTE_CNT + 1)
        item_amount = quantity[i] * item.I_PRICE
        total_amount += item_amount
        d_id_string = str(d_id) if d_id >= 10 else '0' + str(d_id)
        dist_info = getattr(stock, 'S_DIST_' + d_id_string)
        OrderLine.create(OL_O_ID=n, OL_D_ID=d_id, OL_W_ID=w_id, OL_NUMBER=i, OL_I_ID=item_num[i],
                         OL_SUPPLY_W_ID=supplier_warehouse[i], OL_QUANTITY=quantity[i], OL_AMOUNT=item_amount,
                         OL_DIST_INFO=dist_info)
        total_amount = total_amount * (1 + district.D_TAX + warehouse.W_TAX) * (1 - customer.C_DISCOUNT)

    # Output

    print 'customer identifier:', w_id, d_id, c_id, ', last name:', customer.C_LAST, ', credit:', customer.C_CREDIT, ', discount:', customer.C_DISCOUNT
    print 'warehouse tax rate:', warehouse.W_TAX, ', district tax rate:', district.D_TAX
    print 'order number:', n, ', entry date:', entry_time
    print 'number of items:', num_items, ', total amount:', total_amount
    for i in range(num_items):
        item = Item.filter(I_ID=item_num[i]).consistency(READ_CONSISTENCY).get()
        stock = Stock.filter(S_W_ID=w_id, S_I_ID=item_num[i]).consistency(READ_CONSISTENCY).get()
        order_line = OrderLine.filter(OL_O_ID=n, OL_D_ID=d_id, OL_W_ID=w_id, OL_NUMBER=i).consistency(
            READ_CONSISTENCY).get()
        print 'item number:', item_num[i], ', item name:', item.I_NAME, ', supplier warehouse:', supplier_warehouse[
            i], ', quantity:', quantity[i], ', amount:', order_line.OL_AMOUNT, ', stock quantity:', stock.S_QUANTITY


def payment_transaction(c_w_id, c_d_id, c_id, payment):
    warehouse = Warehouse.filter(W_ID=c_w_id).consistency(WRITE_CONSISTENCY).get()
    district = District.filter(D_W_ID=c_w_id, D_ID=c_d_id).consistency(WRITE_CONSISTENCY).get()
    customer = Customer.filter(C_W_ID=c_w_id, C_D_ID=c_d_id, C_ID=c_id).consistency(WRITE_CONSISTENCY).get()
    payment_dec = decimal.Decimal(payment)

    warehouse.update(W_YTD=warehouse.W_YTD + payment_dec)
    district.update(D_YTD=district.D_YTD + payment_dec)
    customer.update(C_BALANCE=customer.C_BALANCE - payment_dec, C_YTD_PAYMENT=customer.C_YTD_PAYMENT + payment,
                    C_PAYMENT_CNT=customer.C_PAYMENT_CNT + 1)

    # Output

    print 'customer identifier:', c_w_id, c_d_id, c_id, ', name:', customer.C_FIRST, customer.C_MIDDLE, customer.C_LAST, ', address:', customer.C_STREET1, customer.C_STREET2, customer.C_CITY, customer.C_STATE, customer.C_ZIP, ', phone:', customer.C_PHONE, ', date and time when entry was created:', customer.C_SINCE, ', credit:', customer.C_CREDIT, ', credit limit', customer.C_CREDIT_LIM, ', discount:', customer.C_DISCOUNT, ', balance:', customer.C_BALANCE
    print 'warehouse address:', warehouse.W_STREET1, warehouse.W_STREET2, warehouse.W_CITY, warehouse.W_STATE, warehouse.W_ZIP
    print 'district address:', district.D_STREET1, district.D_STREET2, district.D_CITY, district.D_STATE, district.D_ZIP
    print 'payment amount:', payment


def delivery_transaction(w_id, carrier_id):
    # Processing steps

    for district_no in range(1, 11):
        orders = Order.filter(O_W_ID=w_id, O_D_ID=district_no).consistency(WRITE_CONSISTENCY)
        for order in orders:
            if order.O_CARRIER_ID is None:
                c = Customer.filter(C_W_ID=w_id, C_D_ID=district_no, C_ID=order.O_C_ID).consistency(
                    WRITE_CONSISTENCY).get()
                order.update(O_CARRIER_ID=carrier_id)
                order_lines = OrderLine.filter(OL_W_ID=w_id, OL_D_ID=district_no, OL_O_ID=order.O_ID).consistency(
                    WRITE_CONSISTENCY)
                b = 0
                for order_line in order_lines:
                    order_line.update(OL_DELIVERY_D=datetime.utcnow())
                    b = b + order_line.OL_AMOUNT
                c.update(C_BALANCE=c.C_BALANCE + b)
                c.update(C_DELIVERY_CNT=c.C_DELIVERY_CNT + 1)
                return


def order_status_transaction(c_w_id, c_d_id, c_id):
    customer = Customer.filter(C_W_ID=c_w_id, C_D_ID=c_d_id, C_ID=c_id).consistency(READ_CONSISTENCY).get()

    # Output
    print 'customer name:', customer.C_FIRST, customer.C_MIDDLE, customer.C_LAST, ', balance:', customer.C_BALANCE
    order = Order.filter(O_W_ID=c_w_id, O_D_ID=c_d_id, O_C_ID=c_id).consistency(READ_CONSISTENCY)[-1]
    print 'order number:', order.O_ID, ', entry date and time:', order.O_ENTRY_D, ', carrier identifier:', order.O_CARRIER_ID
    order_lines = OrderLine.filter(OL_W_ID=c_w_id, OL_D_ID=c_d_id, OL_O_ID=order.O_ID).consistency(READ_CONSISTENCY)
    for order_line in order_lines:
        print 'item number:', order_line.OL_I_ID, ',supplying warehouse number:', order_line.OL_SUPPLY_W_ID, 'quantity ordered:', order_line.OL_QUANTITY, 'total price for ordered item:', order_line.OL_AMOUNT, 'data and time of delivery:', order_line.OL_DELIVERY_D


def stock_level_transaction(w_id, d_id, threshold, last):
    # Processing steps
    orders = Order.filter(O_D_ID=d_id, O_W_ID=w_id).consistency(READ_CONSISTENCY)[-last:]
    items = set()
    for order in orders:
        order_lines = OrderLine.filter(OL_D_ID=d_id, OL_W_ID=w_id, OL_O_ID=order.O_ID).consistency(READ_CONSISTENCY)
        for order_line in order_lines:
            items.add(order_line.OL_I_ID)
    total_number = 0
    for item in items:
        stock = Stock.filter(S_W_ID=w_id, S_I_ID=item).consistency(READ_CONSISTENCY).get()
        if stock.S_QUANTITY < threshold:
            total_number = total_number + 1
    print 'total number of items below the threshold:', total_number


def popular_item_transaction(w_id, d_id, last):
    # Processing steps & Output
    print 'district identifier:', w_id, d_id
    print 'number of last orders to be examined:', last

    orders = Order.filter(O_W_ID=w_id, O_D_ID=d_id).consistency(READ_CONSISTENCY)[-last:]
    popular_items = set()
    items_by_order = []
    for order in orders:
        print 'order number:', order.O_ID, ', entry date and time:', order.O_ENTRY_D
        customer = Customer.filter(C_W_ID=w_id, C_D_ID=d_id, C_ID=order.O_C_ID).consistency(READ_CONSISTENCY).get()
        print 'name of the customer who placed this order:', customer.C_FIRST, customer.C_MIDDLE, customer.C_LAST

        order_lines = OrderLine.filter(OL_W_ID=w_id, OL_D_ID=d_id, OL_O_ID=order.O_ID).consistency(READ_CONSISTENCY)
        max_qty = 0
        popular_ols = []
        items = set()
        for order_line in order_lines:
            items.add(order_line.OL_I_ID)
            if order_line.OL_QUANTITY > max_qty:
                max_qty = order_line.OL_QUANTITY
                popular_ols = [order_line.OL_NUMBER]
            elif order_line.OL_QUANTITY == max_qty:
                popular_ols.append(order_line.OL_NUMBER)

        items_by_order.append(items)
        for popular_ol in popular_ols:
            order_line = OrderLine.filter(OL_W_ID=w_id, OL_D_ID=d_id, OL_O_ID=order.O_ID,
                                          OL_NUMBER=popular_ol).consistency(READ_CONSISTENCY).get()
            item = Item.filter(I_ID=order_line.OL_I_ID).consistency(READ_CONSISTENCY).get()
            print '\titem name:', item.I_NAME, ', quantity ordered:', order_line.OL_QUANTITY
            popular_items.add(item)

    for popular_item in popular_items:
        print 'item name:', popular_item.I_NAME
        count = sum((popular_item.I_ID in items) for items in items_by_order)
        print 'percentage of orders that contain this item:', (count / float(last)) * 100


def top_balance_transaction():
    # Processing steps:
    customers = Customer.all()[:]
    customers.sort(key=lambda x: x.C_BALANCE, reverse=True)

    # Output
    for customer in customers[:10]:
        print "name of the customer:", customer.C_FIRST, customer.C_MIDDLE, customer.C_LAST
        print "balance of the customer's outstanding payment:", customer.C_BALANCE

        warehouse = Warehouse.filter(W_ID=customer.C_W_ID).consistency(READ_CONSISTENCY).get()
        district = District.filter(D_W_ID=customer.C_W_ID, D_ID=customer.C_D_ID).consistency(READ_CONSISTENCY).get()
        print 'warehouse name of customer:', warehouse.W_NAME
        print 'district name of customer:', district.D_NAME


def related_customer_transaction(w_id, d_id, c_id):
    # Processing steps:
    c_orders = Order.filter(O_W_ID=w_id, O_D_ID=d_id, O_C_ID=c_id).consistency(READ_CONSISTENCY)
    c_items_list = []
    for c_order in c_orders:
        c_order_lines = OrderLine.filter(OL_W_ID=w_id, OL_D_ID=d_id, OL_O_ID=c_order.O_ID).consistency(READ_CONSISTENCY)
        c_items = set()
        for c_order_line in c_order_lines:
            c_items.add(c_order_line.OL_I_ID)
        c_items_list.append(c_items)

    related_customers = set()

    orders = Order.all()
    for order in orders:
        if order.O_W_ID == w_id:
            continue
        items = set()
        order_lines = OrderLine.filter(OL_W_ID=order.O_W_ID, OL_D_ID=order.O_D_ID, OL_O_ID=order.O_ID).consistency(
            READ_CONSISTENCY)
        for order_line in order_lines:
            items.add(order_line.OL_I_ID)
        if any(len(c_items.intersection(items)) >= 2 for c_items in c_items_list):
            related_customers.add((order.O_W_ID, order.O_D_ID, order.O_C_ID))

    # Output
    print "customer identifier:", w_id, d_id, c_id
    for related_customer in related_customers:
        print "\trelated customer identifier:", related_customer


if __name__ == '__main__':
    connection.setup(IP_ADDRESS, KEY_SPACE[0])
    new_order_transaction(1, 1, 1279, 2, [68195, 26567], [1, 1], [1, 5])
    payment_transaction(1, 1, 1, 20000.8)
    delivery_transaction(1, 1)
    order_status_transaction(1, 1, 1)
    stock_level_transaction(1, 1, 1000, 50)
    popular_item_transaction(1, 1, 50)
    top_balance_transaction()
    related_customer_transaction(1, 1, 1)
