import os
import sys
import json
import webbrowser
from datetime import datetime, date
import requests
import pygal
from lxml import etree
import csv
from flask import Flask, render_template, request

API_URL = "https://www.alphavantage.co/query"
API_KEY = os.environ.get("ALPHAVANTAGE_API_KEY", "ISKC9Q4DFAEBJCTB")

def validate_date(s: str) -> bool:
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except ValueError:
        return False

def to_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()

def function_for(ts: str) -> str:
    if ts == "DAILY":
        return "TIME_SERIES_DAILY"
    if ts == "WEEKLY":
        return "TIME_SERIES_WEEKLY"
    if ts == "MONTHLY":
        return "TIME_SERIES_MONTHLY"
    raise ValueError("Unsupported time series")

def series_key_for(fn: str) -> str:
    if fn == "TIME_SERIES_DAILY":
        return "Time Series (Daily)"
    if fn == "TIME_SERIES_WEEKLY":
        return "Weekly Time Series"
    if fn == "TIME_SERIES_MONTHLY":
        return "Monthly Time Series"
    raise ValueError("Unsupported function")

def fetch_data(symbol: str, fn: str) -> dict:
    params ={
        "function": fn,
        "symbol": symbol,
        "apikey": API_KEY,
        "datatype": "json",
        "outputsize": "full",
    }
    r = requests.get(API_URL, params=params, timeout=30)
    if r.status_code != 200:
        print("Error fetching data:", r.status_code)
        sys.exit(1)
    data = r.json()
    if "Error Message" in data:
        print("API Error:", data["Error Message"])
        sys.exit(1)
    if "Note" in data:
        print("API Note (rate limited). Please wait ~1 minute and try again.")
        sys.exit(1)
    return data

def parse_close_series(data: dict, fn: str):
    """Return list of (datetime, close) sorted ascending."""
    key = series_key_for(fn)
    if key not in data:
        print("Unexpected API response. missing key:", list(data.keys()))
        sys.exit(1)
    rows = []
    for k, v in data[key].items():
        ts = datetime.strptime(k, "%Y-%m-%d")
        close_str = v.get("4. close", None)
        if close_str is None:
            continue
        try:
            close_val = float(close_str)
            rows.append((ts, close_val))
        except ValueError:
            continue
    rows.sort(key=lambda x: x[0])
    return rows

def filter_range(rows, start_d: date, end_d: date):
    return [(ts, c) for (ts, c) in rows if start_d <= ts.date() <= end_d]

def thin_labels(labels, max_labels=12):
    n = len(labels)
    if n <= max_labels:
        return labels
    step = max(1, n // max_labels)
    return [lbl if (i % step == 0 or i == n-1) else None for i, lbl in enumerate(labels)]

def make_chart(symbol: str, ts_label: str, chart_type: str, rows):
    title = f"{symbol} — {ts_label}"
    x_labels = [d.strftime("%Y-%m-%d") for (d, _c) in rows]
    closes = [c for (_d, c) in rows]

    if chart_type == "line":
        chart = pygal.Line(show_minor_x_labels=False, x_label_rotation=20, show_legend=False)
    else:
        chart = pygal.Bar(show_minor_x_labels=False, x_label_rotation=20, show_legend=False)

    chart.title = title
    chart.x_labels = x_labels
    chart.x_labels_major = [lbl for lbl in thin_labels(x_labels)]
    chart.y_title = "Close (USD)"
    chart.add("Close", closes)
    return chart.render(is_unicode=True)

def wrap_html(svg_text: str, page_title: str) -> str:
    html = etree.Element("html")
    head = etree.SubElement(html, "head")
    etree.SubElement(head, "meta", charset="utf-8")
    title_el = etree.SubElement(head, "title")
    title_el.text = page_title
    style = etree.SubElement(head, "style")
    style.text = "body{font-family:Arial,Helvetica,sans-serif;margin:24px;} .chart{max-width:1000px;}"

    body = etree.SubElement(html, "body")
    h1 = etree.SubElement(body, "h1")
    h1.text = page_title
    chart_div = etree.SubElement(body, "div", attrib={"class": "chart"})

    try:
        svg_el = etree.fromstring(svg_text.encode("utf-8"))
        chart_div.append(svg_el)
    except Exception as e:
        pre = etree.SubElement(chart_div, "pre")
        pre.text = f"(SVG embed error: {e})\n\n{svg_text}"

    return etree.tostring(html, pretty_print=True, encoding="unicode")

def save_and_open(html_text: str, symbol: str):
    fname = f"{symbol}_chart.html"
    with open(fname, "w", encoding="utf-8") as f:
        f.write(html_text)
    webbrowser.open("file://" + os.path.abspath(fname))



def main():
    print("=== Stock Data Visualizer ===")

    stock_symbol = input("Enter stock symbol (e.g., AAPL, GOOGL): ").upper()
    chart_type  = input("Enter chart type (line, bar): ").lower()
    time_series = input("Enter time series (daily, weekly, monthly): ").upper()
    start_date  = input("Enter start date (YYYY-MM-DD): ")
    end_date    = input("Enter end date (YYYY-MM-DD): ")

    if not validate_date(start_date) or not validate_date(end_date):
        print("Invalid date format. Please use YYYY-MM-DD.")
        return
    if start_date > end_date:
        print("Start date must be before end date.")
        return
    if chart_type not in ["line", "bar"]:
        print("Invalid chart type. Please choose 'line' or 'bar'.")
        return
    if time_series not in ["DAILY", "WEEKLY", "MONTHLY"]:
        print("Invalid time series. Please choose 'daily', 'weekly', or 'monthly'.")
        return

    try:
        fn = function_for(time_series)
        data = fetch_data(stock_symbol, fn)
        rows = parse_close_series(data, fn)
        rows = filter_range(rows, to_date(start_date), to_date(end_date))
        if not rows:
            print("No data in that date range.")
            return
        svg = make_chart(stock_symbol, time_series.title(), chart_type, rows)
        page_title = f"{stock_symbol} — {time_series.title()} — {start_date} to {end_date}"
        html_text = wrap_html(svg, page_title)
        save_and_open(html_text, stock_symbol)
        print("Chart generated and opened in your browser.")
    except Exception as e:
        print("Something went wrong:", e)

if __name__ == "__main__":
    main()