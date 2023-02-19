"""Plotting results."""


import plotly.express as px


def plot_timeline(df, end_dt, **kwargs):
    """Plotting categorical data, e.g. states."""
    df = df.assign(
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
    fig.for_each_annotation(
        lambda a: a.update(text=a.text.split(" - ")[-1])
    )
    fig.update_annotations(font_size=8)
    fig.update_yaxes(matches=None)
    fig.show()


def plot_numerical(df, end_dt=None, **kwargs):
    """Plotting numerical data, e.g. container levels."""
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
    fig.update_annotations(font_size=8)
    fig.update_yaxes(matches=None)
    fig.for_each_annotation(
        lambda a: a.update(text=a.text.replace("key=", ""))
    )
    fig.show()
