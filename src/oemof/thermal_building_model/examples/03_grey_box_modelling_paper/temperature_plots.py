import os
import matplotlib.pyplot as plt
import pandas as pd


def plot_zone_temperatures(
    data,
    building="B1",
    results_dir=None,
):
    """
    Plot all measured zone temperatures and the
    area-weighted indoor temperature.
    """

    # ---------------------------------------------------------
    # Tzone-Spalten finden
    # ---------------------------------------------------------

    zone_columns = [
        column
        for column in data.columns
        if column.startswith(f"{building}_")
        and "_Tzone" in column
        and column.endswith("C]")
    ]

    if not zone_columns:
        raise ValueError(
            f"No Tzone columns found for {building}."
        )

    # ---------------------------------------------------------
    # Einzelne Raumtemperaturen
    # ---------------------------------------------------------

    fig, ax = plt.subplots(figsize=(12, 6))

    for column in zone_columns:
        ax.plot(
            data.index,
            pd.to_numeric(
                data[column],
                errors="coerce",
            ),
            label=column,
        )

    ax.set_title(
        f"Measured Zone Temperatures - {building}"
    )

    ax.set_ylabel("Temperature [°C]")
    ax.set_xlabel("Time")

    ax.legend(
        loc="best",
        fontsize=8,
    )

    fig.autofmt_xdate()

    if results_dir is not None:
        fig.savefig(
            os.path.join(
                results_dir,
                f"{building}_zone_temperatures.png",
            ),
            dpi=300,
            bbox_inches="tight",
        )

    plt.show()

    # ---------------------------------------------------------
    # Gewichtete Gesamt-Innentemperatur
    # ---------------------------------------------------------

    if "T_indoor [°C]" in data.columns:

        fig, ax = plt.subplots(figsize=(12, 6))

        ax.plot(
            data.index,
            data["T_indoor [°C]"],
            label="Area-weighted indoor temperature",
        )

        ax.set_title(
            f"Area-weighted Indoor Temperature - {building}"
        )

        ax.set_ylabel("Temperature [°C]")
        ax.set_xlabel("Time")

        ax.legend()

        fig.autofmt_xdate()

        if results_dir is not None:
            fig.savefig(
                os.path.join(
                    results_dir,
                    f"{building}_weighted_indoor_temperature.png",
                ),
                dpi=300,
                bbox_inches="tight",
            )

        plt.show()