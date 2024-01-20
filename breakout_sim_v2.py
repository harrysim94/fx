import utils
import datetime
import pandas as pd
import instrument
import plotly.graph_objects as go

BUY = 1
SELL = -1


def is_weekday(date):
    if date.weekday() < 5:
        return True
    return False


def get_date_as_string(df):
    start_date = df.loc[0, "time"].strftime("%Y-%m-%d")
    end_date = df.loc[(len(df.index) - 1), "time"].strftime("%Y-%m-%d")
    if start_date != end_date:
        raise Exception("Error: Dataframe does not start and end on the same day")
    return start_date


def get_close_time_as_string(df):
    close_time = df.loc[(len(df.index) - 1), "time"].strftime("%H:%M:%S")
    return close_time


def exit_time(df):
    return utils.get_utc_dt_from_string(
        f"{get_date_as_string(df)} {get_close_time_as_string(df)}"
    )


def get_past_data(df, index):
    return df.iloc[:index].copy()


def count_open_trades(df):
    buy_list = [x for x in df.IS_TRADE if x == BUY]
    sell_list = [x for x in df.IS_TRADE if x == SELL]
    buys = len(buy_list)
    sells = len(sell_list)
    return {"total": (buys + sells), "buys": buys, "sells": sells}


def over_range_max(row, range_max):
    return row.mid_o >= range_max and row.mid_c > range_max


def under_range_min(row, range_min):
    return row.mid_o <= range_min and row.mid_c < range_min


def inside_range(row, range_min, range_max):
    # check_open = row.mid_o > range_min and row.mid_o < range_max
    check_close = row.mid_c > range_min and row.mid_c < range_max
    return check_close


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


def get_post_london_open_data(df):
    day = get_date_as_string(df)
    london_start_time = utils.get_utc_dt_from_string(f"{day} 07:00:00+00:00")
    df_post_london_open = df[(df.time >= london_start_time)].copy()
    df_post_london_open.reset_index(drop=True, inplace=True)
    return df_post_london_open


def calculate_pre_open_range(df_day):
    day = get_date_as_string(df_day)
    asia_start_time = utils.get_utc_dt_from_string(f"{day} 00:00:00+00:00")
    london_start_time = utils.get_utc_dt_from_string(f"{day} 07:00:00+00:00")
    df_pre_london_open = df_day[
        (df_day.time >= asia_start_time) & (df_day.time < london_start_time)
    ].copy()
    range_max = max(df_pre_london_open.mid_c.max(), df_pre_london_open.mid_o.max())
    range_min = min(df_pre_london_open.mid_c.min(), df_pre_london_open.mid_o.min())
    return range_min, range_max


def calculate_trades(df, range_min, range_max):
    df["IS_TRADE"] = 0
    for index, row in df.iterrows():
        trade_count = count_open_trades(get_past_data(df, index))
        if over_range_max(row, range_max):
            if trade_count["buys"] == 0:
                df.loc[index, "IS_TRADE"] = BUY
        elif under_range_min(row, range_min):
            if trade_count["sells"] == 0:
                df.loc[index, "IS_TRADE"] = SELL
        elif inside_range(row, range_min, range_max):
            if trade_count["buys"] == 1 and trade_count["total"] == 1:
                df.loc[index, "IS_TRADE"] = SELL
            if trade_count["sells"] == 1 and trade_count["total"] == 1:
                df.loc[index, "IS_TRADE"] = BUY
        if row.time >= exit_time(df):
            if trade_count["total"] == 1:
                if trade_count["buys"] == 1:
                    df.loc[index, "IS_TRADE"] = SELL
                if trade_count["sells"] == 1:
                    df.loc[index, "IS_TRADE"] = BUY
    return df


def process_trades(df, i_pair):
    df_trades = df[df.IS_TRADE != 0].copy()
    df_trades["DELTA"] = df_trades.mid_c.diff() / i_pair.pipLocation
    df_trades["GAIN"] = df_trades["DELTA"] * df_trades["IS_TRADE"] * (-1)
    return df_trades


def run_pair(start_date, end_date, pairname, granularity):
    price_data = get_price_data(pairname, granularity)
    i_pair = instrument.Instrument.get_instruments_dict()[pairname]
    start_date = utils.get_utc_dt_from_string(start_date)
    end_date = utils.get_utc_dt_from_string(end_date)
    day_count = (end_date - start_date).days - 1
    days = []
    results = []
    for date in (start_date + datetime.timedelta(n) for n in range(day_count)):
        days.append(date)
        if is_weekday(date):
            df = get_day_data(date, price_data)
            # df = get_post_london_open_data(df)
            open_range = calculate_pre_open_range(df)
            df = calculate_trades(df, range_min=open_range[0], range_max=open_range[1])
            df_trades = process_trades(df, i_pair)
            if len(df_trades.IS_TRADE.values.tolist()) == 2:
                gain = round(df_trades["GAIN"].iloc[-1], 5)
            elif len(df_trades.IS_TRADE.values.tolist()) == 0:
                gain = 0
            results.append(gain)
        else:
            results.append(0.0)
    df_results = pd.DataFrame({"date": days, "pips": results})
    df_results["gain"] = df_results.pips.cumsum()
    return df_results


if __name__ == "__main__":
    granularity = "M5"
    start_date = "2018-01-02"
    end_date = "2020-06-02"
    pairs = [
        "GBP_USD",
        # "GBP_CAD",
        # "GBP_JPY",
        "GBP_NZD",
        # "GBP_CHF",
    ]

    fig = go.Figure()
    for pairname in pairs:
        df_results = run_pair(start_date, end_date, pairname, granularity)

        fig.add_trace(
            go.Scatter(
                x=df_results.date,
                y=df_results.gain,
                line=dict(width=2),
                line_shape="linear",
                name=pairname,
            )
        )
    # fig.add_trace(
    #     go.Scatter(
    #         x=df_results.date,
    #         y=df_results.pips,
    #         line=dict(width=2),
    #         line_shape="spline",
    #     )
    # )
    fig.show()
