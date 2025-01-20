range_upper = 187.741
range_lower = 187.443
pre_range = range_upper - range_lower

buy_take_profit = range_upper + 2.0*pre_range
buy_stop_loss = range_upper - pre_range/2

sell_take_profit = range_lower - 2.0*pre_range
sell_stop_loss = range_lower + pre_range/2

print(f"RANGE: {pre_range*100} pips")
print(f"BUY: TP = {buy_take_profit}, SL = {buy_stop_loss}")
print(f"SELL: - TP = {sell_take_profit}, SL = {sell_stop_loss}")