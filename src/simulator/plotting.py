"""Plotting results."""


import pandas as pd
import plotly.express as px


def plot_timeline(data, end_dt, **kwargs):
    """Plotting categorical data, e.g. states."""
    df = pd.DataFrame(data, columns=["ds", "obj", "key", "value"]).assign(
        name=lambda df_: df_["obj"] + " - " + df_["key"],
        end_ts=lambda df_: df_.groupby(["obj", "key"])["ds"]
        .shift(-1)
        .fillna(end_dt),
        value=lambda df_: df_["value"].astype(str),
    )
    if df.empty:
        return

    n_plots = (
        df["name"].nunique() * df.groupby("name")["value"].nunique().mean()
    )
    fig = px.timeline(
        df,
        facet_row="name",
        x_start="ds",
        x_end="end_ts",
        y="value",
        title="Simulation - Categorical",
        color="obj",
        height=n_plots * 100,
        **kwargs,
    )
    fig.for_each_annotation(lambda a: a.update(text=a.text.split(" - ")[-1]))
    fig.update_yaxes(matches=None)
    fig.show()


def plot_numerical(data, end_dt=None, **kwargs):
    """Plotting numerical data, e.g. container levels."""
    df = pd.DataFrame(data, columns=["ds", "obj", "key", "value"])
    df["end_ts"] = df["ds"].shift(-1).fillna(end_dt)
    if df.empty:
        return

    n_plots = df["key"].nunique()
    fig = px.line(
        df,
        x="ds",
        y="value",
        color="obj",
        facet_row="key",
        title="Simulation - Numerical",
        height=n_plots * 150,
        **kwargs,
    )
    fig.update_yaxes(matches=None)
    fig.for_each_annotation(
        lambda a: a.update(text=a.text.replace("key=", ""))
    )
    fig.show()


def extract_dict_data(obj_dict):
    categorical = []
    numerical = []
    for obj_id, obj in obj_dict.items():
        categorical += obj.data["categorical"]
        numerical += obj.data["numerical"]

    return categorical, numerical


def extract_list_data(obj_list):
    categorical = []
    numerical = []
    for obj in obj_list:
        categorical += obj.data["categorical"]
        numerical += obj.data["numerical"]

    return categorical, numerical


def plot_factory(factory):
    categorical = []
    numerical = []
    end_dt = factory.now_dt.datetime
    obj_types = [
        "machines",
        "operators",
        "containers",
        "maintenance",
        "programs",
        "schedules",
        "sensors",
    ]
    for obj_type in obj_types:
        if hasattr(factory, obj_type):
            data_or_obj = getattr(factory, obj_type)
        else:
            continue

        # Extract data depending on object
        if isinstance(data_or_obj, dict):
            cat, num = extract_dict_data(data_or_obj)
        elif isinstance(data_or_obj, list):
            cat, num = extract_list_data(data_or_obj)
        elif hasattr("data", data_or_obj):
            data = data_or_obj.data
            cat = data["categorical"]
            num = data["numerical"]
        else:
            print(f'Dont know how to extract data from "{type(data)}"')

        categorical += cat
        numerical += num

    plot_timeline(categorical, end_dt, width=800)
    plot_numerical(numerical, end_dt, width=800)
