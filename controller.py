import asyncio
from datetime import date
from pathlib import Path
from typing import Optional

import geopandas as gpd
import holoviews as hv
import panel as pn
import param


class Dashboard:
    """Arranges UI and updates data in place."""

    def __init__(self, data_cache, plotter, streamer):

        self.data_cache = data_cache
        self.plotter = plotter
        self.streamer = streamer

        self.plots_oggm_container = pn.FlexBox(
            pn.Column(pn.pane.Markdown("### Select a glacier to view data")),
            sizing_mode="stretch_width",
            styles=self.get_flex_styling(),
        )
        self.plots_cryosat_container = pn.Column(
            pn.pane.Markdown("### No CryoSat data available.", name="CryoSat Data"),
            sizing_mode="stretch_width",
            styles=self.get_flex_styling(),
        )
        self.map = pn.FlexBox(pn.pane.Markdown(f"""Test init"""))
        self.glacier_info = pn.pane.HTML()

        pn.io.loading.start_loading_spinner(self.plots_oggm_container)
        glacier_index = self.data_cache.get_glacier_index()
        regions = list(glacier_index.keys())

        self.region_selector = pn.widgets.Select(
            name="Region", options=regions, value=regions[0]
        )
        self.glacier_selector = pn.widgets.Select(
            name="Glacier",
            options=list(glacier_index[regions[0]].keys()),
            value=list(glacier_index[regions[0]].keys())[0],
        )
        self.year_selector = pn.widgets.Select(
            name="Year",
            options=list(range(int(date.today().year) - 1, 1999, -1)),
            value=int(date.today().year) - 1,
        )
        self.model_selector = pn.widgets.Select(
            name="OGGM Model",
            options={
                "Daily": "DailyTIModel",
                "Daily Surface Tracking": "SfcTypeTIModel",
            },
            value="DailyTIModel",
        )

        self._glacier_index = glacier_index
        self._current_data: Optional[dict] = None
        self._current_rgi_id: Optional[str] = None
        self._current_year: Optional[str] = None
        self._current_model: Optional[str] = None
        self._current_shapefile: Optional[hv.Polygons] = None

        # Sidebar menus
        self.region_selector.param.watch(self._on_region_change, ["value"])
        self.glacier_selector.param.watch(self._on_glacier_change, ["value"])
        self.year_selector.param.watch(self._on_year_change, ["value"])
        self.model_selector.param.watch(self._on_model_change, ["value"])

        self.region_selector.param.trigger("options", "value")
        self.glacier_selector.param.trigger("options", "value")

        self.progress_bar = pn.indicators.Progress(
            name="Retrieving Data...", active=True, value=0
        )
        self.download_button = self.set_download_button()
        pn.io.loading.stop_loading_spinner(self.plots_oggm_container)
        pn.io.loading.stop_loading_spinner(self.plots_cryosat_container)

    def get_flex_styling(self, style=None) -> dict:
        """Get CSS styling for flex boxes.

        .. note:: Not-so-temporary workaround for unsolved bugs in
        Panel:
           - https://github.com/holoviz/panel/issues/5343
           - https://github.com/holoviz/panel/issues/5054
           - https://github.com/holoviz/panel/issues/1296
        """
        if not style:
            style = {
                "flex": "1 1 auto",
                "align-items": "stretch",
                "align-content": "flex-start",
                "flex-wrap": "nowrap",
            }

        return style

    def _on_region_change(self, *events):
        """Callback for when the region changes."""
        region = self.region_selector.value
        glaciers = list(self._glacier_index[region].keys())
        self._current_shapefile = self.data_cache.get_cached_region_outlines(
            region_id=region
        )

        self.glacier_selector.options = glaciers
        # Async causes blank plots if glacier change not triggered.
        self.glacier_selector.value = glaciers[0]

    async def _on_year_change(self, *events):
        """Callback for when the year changes."""
        self._current_year = self.year_selector.value
        try:
            self._update_plots()
        finally:
            pn.io.loading.stop_loading_spinner(self.plots_oggm_container)
            pn.io.loading.stop_loading_spinner(self.plots_cryosat_container)
            self.disable_selectors(disabled=False)

    async def _on_model_change(self, *events):
        """Callback for when the model changes."""
        self._current_model = self.model_selector.value
        try:
            self._update_plots()
        finally:
            pn.io.loading.stop_loading_spinner(self.plots_oggm_container)
            pn.io.loading.stop_loading_spinner(self.plots_cryosat_container)
            self.disable_selectors(disabled=False)

    async def _on_glacier_change(self, *events):
        """Callback for when the glacier changes."""
        glacier = self.glacier_selector.value
        region = self.region_selector.value
        year = self.year_selector.value
        model = self.model_selector.value

        # Get RGI ID
        rgi_id = self._glacier_index[region][glacier]

        try:
            # Load data asynchronously
            data = await self.data_cache.get_glacier_data(rgi_id)

            # Store current data
            self._current_data = data
            self._current_rgi_id = rgi_id
            self._current_year = year
            self._current_model = model

            # TODO: Implement asyncio for performance
            self.set_map()
            self._update_plots()

            self.download_button = self.set_download_button()

        finally:
            # Hide loading indicator
            pn.io.loading.stop_loading_spinner(self.plots_oggm_container)
            pn.io.loading.stop_loading_spinner(self.plots_cryosat_container)
            self.disable_selectors(disabled=False)

    def _update_plots(self):
        glacier = self.glacier_selector.value
        model = self.model_selector.value
        figures_l2 = self.plotter.create_l2_plots(
            data=self._current_data, year=self._current_year, model_name=model
        )

        with param.parameterized.batch_call_watchers(self.plots_oggm_container):
            oggm_objects = [
                pn.pane.Markdown(
                    f"### {glacier} ({self._current_year})",
                    sizing_mode="stretch_width",
                    styles=self.get_flex_styling(),
                ),
                *figures_l2,
            ]
            self.plots_oggm_container.objects = oggm_objects
        self.glacier_info.object = self.set_details(self._current_data)

        figures_l1 = self.plotter.create_l1_plots(
            data=self._current_data, year=self._current_year
        )
        if figures_l1:
            with param.parameterized.batch_call_watchers(self.plots_cryosat_container):
                cryosat_objects = [
                    pn.pane.Markdown(f"### {glacier} ({self._current_year})"),
                    *figures_l1,
                ]
                self.plots_cryosat_container.objects = cryosat_objects

        return figures_l1, figures_l2

    def set_map(self):
        """Set map selection pane."""
        try:
            if self._current_shapefile is not None:
                glacier_map = pn.panel(
                    self.plotter.plot_selection_map(
                        shapefile=self._current_shapefile,
                        rgi_id=self._current_rgi_id,
                        region_name=self.region_selector.value,
                    ).opts(max_width=250)
                )
                self.map[:] = glacier_map
            else:
                self.map.objects = [pn.pane.Markdown(f"""No shapefile""")]
        except Exception as e:
            self.map.objects = [pn.pane.Markdown(f"""Map not loaded: {e}""")]
        return self.map

    def set_details(self, data):
        """Set glacier details pane."""

        if data is not None:
            details = self.get_outline_details(polygon=data["outlines"].iloc[0])
            table = ""
            for k, v in details.items():
                if isinstance(v["value"], float):
                    value = f"{v['value']:.2f}"
                else:
                    value = v["value"]
                table_row = (
                    f"<tr><th>{k}</th><td>{' '.join((f'{value}', v['unit']))}</td></tr>"
                )
                table = f"{table}{table_row}"

            details = (
                f"<hr></hr><h2>Glacier Details</h2><table>{table}</table><hr></hr>"
            )
        return details

    def get_outline_details(self, polygon) -> dict:
        outline_details = {
            "Name": {"value": polygon["Name"], "unit": ""},
            "RGI ID": {"value": polygon["RGIId"], "unit": ""},
            "GLIMS ID": {"value": polygon["GLIMSId"], "unit": ""},
            "Area": {"value": float(polygon["Area"]), "unit": "km²"},
            "Max Elevation": {"value": polygon["Zmax"], "unit": "m"},
            "Min Elevation": {"value": polygon["Zmin"], "unit": "m"},
            "Latitude": {"value": float(polygon["CenLat"]), "unit": "°N"},
            "Longitude": {"value": float(polygon["CenLon"]), "unit": "°E"},
            "Outline Date": {
                "value": self.get_outline_source_date(polygon),
                "unit": "",
            },
        }
        return outline_details

    def get_outline_source_date(self, glacier_data: gpd.GeoDataFrame) -> int:
        """Get the date for an outline's source.

        Parameters
        ----------
        glacier_data : gpd.GeoDataFrame
            Outline data for a glacier. Must conform to
            `RGI60 specifications <https://www.glims.org/RGI/00_rgi60_TechnicalNote.pdf>`__.

        Returns
        -------
        int
            The year the outline's source data was published.
        """
        outline_date = glacier_data.get("EndDate", "-9999999")
        if outline_date == "-9999999":
            outline_date = glacier_data.get("BgnDate", "-9999999")
        outline_date = int(outline_date[:4])

        return outline_date

    async def get_zipped_datacube(
        self, rgi_id, zip_path=Path("./static/data/zarr_data/")
    ) -> Path:
        path = self.streamer.get_zip_path(
            zip_path=zip_path, rgi_id=self._current_rgi_id
        )
        self.download_button.disabled = True
        self.disable_selectors(disabled=True)
        self.progress_bar.value = -1
        try:
            path = await asyncio.to_thread(
                self.streamer.zip_datacube(
                    zip_path=zip_path, rgi_id=self._current_rgi_id
                )
            )
        except FileNotFoundError as e:
            pn.state.notifications.position = "bottom-left"
            pn.state.notifications.error(
                "No datacube available for this glacier.", duration=3000
            )
            path = ""
        finally:
            self.download_button.disabled = False
            self.disable_selectors(disabled=False)
            self.progress_bar.value = 0
            # returns in finally blocks will deprecate with Python 3.15
            return path  # avoid unbound local errors and other such things

    def get_filename(self):
        filename = f"{self._current_rgi_id}.zarr.zip"
        return filename

    def set_download_button(self):
        self.download_button = pn.widgets.FileDownload(
            callback=pn.bind(self.get_zipped_datacube, rgi_id=self._current_rgi_id),
            # filename=f"{self._current_rgi_id}.zarr.zip",
            label="Download Datacube",
        )

        return self.download_button

    def display_loading_indicator(self, glacier, year, model, *events):
        pn.io.loading.start_loading_spinner(self.plots_oggm_container)
        pn.io.loading.start_loading_spinner(self.plots_cryosat_container)
        self.disable_selectors(disabled=True)

    def disable_selectors(self, disabled=True, *events):
        for selector in [
            self.glacier_selector,
            self.year_selector,
            self.region_selector,
            self.model_selector,
        ]:
            selector.disabled = disabled

    def build_dashboard(self) -> pn.template.MaterialTemplate:
        """Compose the dashboard."""

        sidebar = pn.Column(
            pn.pane.Markdown("### Glacier Selection"),
            self.region_selector,
            self.glacier_selector,
            self.year_selector,
            self.model_selector,
            self.map,
            self.glacier_info,
            self.progress_bar,
            self.download_button,
            sizing_mode="stretch_width",
        )

        main = pn.Column(
            pn.Tabs(
                (
                    "Model (OGGM)",
                    pn.Column(
                        pn.param.ParamFunction(
                            pn.bind(
                                self.display_loading_indicator,
                                glacier=self.glacier_selector,
                                year=self.year_selector,
                                model=self.model_selector,
                            ),
                            loading_indicator=False,
                        ),
                        self.plots_oggm_container,
                    ),
                ),
                ("EO (Cryosat)", self.plots_cryosat_container),
                styles={
                    "flex": "0 0 auto",
                    "align-items": "stretch",
                    "align-content": "stretch",
                    "flex-wrap": "nowrap",
                },
                sizing_mode="stretch_width",
            ),
            styles={
                "flex": "1 1 auto",
                "align-items": "stretch",
                "align-content": "stretch",
                "flex-wrap": "nowrap",
            },
            sizing_mode="stretch_width",
        )

        template = pn.template.MaterialTemplate(
            title="Alpine and Icelandic Glacier Dashboard",
            busy_indicator=pn.indicators.LoadingSpinner(size=40),
            sidebar=sidebar,
            main=main,
            logo="./static/img/dtc_logo_inv_min.png",
            sidebar_width=250,
        )

        return template
