import utils
import datetime
import pandas as pd
import instrument


def is_weekday(date):
    if date.weekday() < 5:
        return True
    return False


def is_trade(row):
    if row.CROSS_MAX == True:
        # Buy
        return 1
    if row.CROSS_MIN == True:
        # Sell
        return -1
    return 0


def get_date_as_string(df):
    start_date = df.loc[0, "time"].strftime("%Y-%m-%d")
    end_date = df.loc[(len(df.index) - 1), "time"].strftime("%Y-%m-%d")
    if start_date != end_date:
        raise Exception("Error: Dataframe does not start and end on the same day")
    return start_date


def get_close_time_as_string(df):
    close_time = df.loc[(len(df.index) - 1), "time"].strftime("%H:%M:%S")
    return close_time


def get_price_data(pairname, granularity):
    df = pd.read_pickle(utils.get_his_data_filename(pairname, granularity))
    non_cols = ["time", "volume"]
    mod_cols = [x for x in df.columns if x not in non_cols]
    df[mod_cols] = df[mod_cols].apply(pd.to_numeric)
    return df[["time", "mid_o", "mid_h", "mid_l", "mid_c"]]


def get_day_data(date, price_data):
    start_time = date
    end_time = start_time + datetime.timedelta(days=1)
    df_day = price_data[
        (price_data.time >= start_time) & (price_data.time < end_time)
    ].copy()
    df_day.dropna(inplace=True)
    df_day.reset_index(drop=True, inplace=True)
    return df_day


def calculate_pre_open_range(df_day):
    day = get_day_as_string(df_day)
    asia_start_time = utils.get_utc_dt_from_string(f"{day} 00:00:00+00:00")
    london_start_time = utils.get_utc_dt_from_string(f"{day} 07:00:00+00:00")
    df_pre_london_open = df_day[
        (df_day.time >= asia_start_time) & (df_day.time < london_start_time)
    ].copy()
    range_max = max(df_pre_london_open.mid_c.max(), df_pre_london_open.mid_o.max())
    range_min = min(df_pre_london_open.mid_c.min(), df_pre_london_open.mid_o.min())
    return range_min, range_max


def calaculate_day_closing_price(df_day):
    day = get_day_as_string(df_day)
    i = df_day.index[
        df_day["time"]
        == utils.get_utc_dt_from_string(
            f"{get_day_as_string(df_day)} {get_close_time_as_string(df_day)}"
        )
    ].tolist()
    i = i.pop()
    return df_day.loc[i, "mid_c"]


def calculate_trades(df_day, range, i_pair):
    range_min, range_max = range[0], range[1]

    # Find candles fully over or under the thresholds
    df_day["OVER_MAX"] = (df_day.mid_o >= range_max) & (df_day.mid_c > range_max)
    df_day["OVER_MAX_PREV"] = df_day.OVER_MAX.shift(1)
    df_day["UNDER_MIN"] = (df_day.mid_o <= range_min) & (df_day.mid_c < range_min)
    df_day["UNDER_MIN_PREV"] = df_day.UNDER_MIN.shift(1)

    # Shift and compare to find first True instance
    df_day["CROSS_MAX"] = (df_day.OVER_MAX == True) & (df_day.OVER_MAX_PREV == False)
    df_day["CROSS_MIN"] = (df_day.UNDER_MIN == True) & (df_day.UNDER_MIN_PREV == False)

    # Convert cross points into buy/sell signals
    df_day["IS_TRADE"] = df_day.apply(is_trade, axis=1)

    # Remove unused columns
    del df_day["OVER_MAX"]
    del df_day["OVER_MAX_PREV"]
    del df_day["UNDER_MIN"]
    del df_day["UNDER_MIN_PREV"]
    del df_day["CROSS_MAX"]
    del df_day["CROSS_MIN"]

    # Add exit trade at last time point
    i = df_day.index[
        df_day["time"]
        == utils.get_utc_dt_from_string(
            f"{get_day_as_string(df_day)} {get_close_time_as_string(df_day)}"
        )
    ].tolist()
    trades = [x for x in df_day.IS_TRADE if x != 0]
    last_trade = trades[-1:].pop()
    df_day.loc[i.pop(), "IS_TRADE"] = (-1) * last_trade

    df_trades = df_day[df_day.IS_TRADE != 0].copy()
    df_trades["DELTA"] = df_trades.mid_c.diff() / i_pair.pipLocation
    df_trades["GAIN"] = df_trades["DELTA"] * df_trades["IS_TRADE"] * (-1)

    return df_trades


pairname = "GBP_USD"
granularity = "M5"
start_date = "2018-01-02"
end_date = "2020-12-31"

price_data = get_price_data(pairname, granularity)
i_pair = instrument.Instrument.get_instruments_dict()[pairname]

start_date = utils.get_utc_dt_from_string(start_date)
end_date = utils.get_utc_dt_from_string(end_date)
day_count = (end_date - start_date).days + 1

i = 0
count = 0

for date in (start_date + datetime.timedelta(n) for n in range(day_count)):
    if is_weekday(date):
        print("Trading Day:", date.strftime("%Y-%m-%d"))
        df_day = get_day_data(date, price_data)
        opening_range = calculate_pre_open_range(df_day)
        df_trades = calculate_trades(df_day, opening_range, i_pair)

        print(df_trades.head())

        # close_price = calaculate_day_closing_price(df_day)
        # opening_range_mid = (opening_range[1] + opening_range[0]) / 2
        # delta = close_price - opening_range_mid
        # range_delta = (opening_range[1] - opening_range[0]) / i_pair.pipLocation
        # pip_change = abs(delta / i_pair.pipLocation)
        # count += pip_change - range_delta
        # print("Open Trade:", opening_range_mid)
        # print("Close Trade:", close_price)
        # print("Pip-Delta:", pip_change)
        # print("Range Delta:", range_delta)

    else:
        print("Weekend Day:", date.strftime("%Y-%m-%d"))

    i += 1
    if i == 30:
        break

print("\n")
print("Total Pip Count:", count)
