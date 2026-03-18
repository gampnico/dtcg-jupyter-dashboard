import dtcg.interface.plotting as dtcg_plotting
import geoviews as gv
import holoviews as hv
import panel as pn

# Configure panel
pn.extension("notifications")
pn.extension(design="material", sizing_mode="stretch_width")


class GlacierPlotter:
    """Create plots."""

    def __init__(self):
        self.plot_cryo = dtcg_plotting.BokehSynthetic()
        self.plot_map = dtcg_plotting.BokehMapOutlines()
        self.plot_graph = dtcg_plotting.BokehGraph()
        self.palette = self.plot_map.palette
        # self.tooltips = self.plot_map.tooltips
        # self.hover_tool = self.plot_map.hover_tool

    def create_l2_plots(
        self, data: dict, year: int, model_name: str = "DailyTIModel"
    ) -> tuple:
        """Create L2 Bokeh plots from data."""
        gdir = data["gdir"]
        datacube = data.get("eolis", None)
        smb = data["smb"]
        runoff_data = data["runoff_data"]["Daily_Hugonnet_2000_2020"]
        figures = []

        fig_daily_mb = self.plot_cryo.plot_mb_comparison(
            smb=smb,
            ref_year=year,
            datacube=datacube,
            gdir=gdir,
            cumulative=False,
            model_name=model_name,
        )
        fig_cumulative_mb = self.plot_cryo.plot_mb_comparison(
            smb=smb,
            ref_year=year,
            datacube=datacube,
            gdir=gdir,
            cumulative=True,
            model_name=model_name,
        )

        fig_monthly_runoff = self.plot_graph.plot_runoff_timeseries(
            runoff=runoff_data["monthly_runoff"], ref_year=year, nyears=27
        )
        fig_runoff_cumulative = self.plot_graph.plot_runoff_timeseries(
            runoff=runoff_data["monthly_runoff"],
            ref_year=year,
            cumulative=True,
            nyears=27,
        )
        if datacube is not None:
            model = "OGGM + CryoSat"
        else:
            model = "OGGM"

        figures = [
            pn.pane.HoloViews(
                fig_daily_mb.opts(title=f"Specific Mass Balance ({model})")
            ),
            pn.pane.HoloViews(
                fig_cumulative_mb.opts(
                    title=f"Cumulative Specific Mass Balance ({model})"
                )
            ),
            pn.pane.HoloViews(fig_monthly_runoff),
            pn.pane.HoloViews(fig_runoff_cumulative),
        ]

        return figures

    def create_l1_plots(self, data: dict, year: int) -> tuple:
        """Create L1 Bokeh plots from data."""
        gdir = data["gdir"]
        datacube = data.get("eolis", None)

        figures = []
        if datacube is not None:
            fig_eo_elevation = self.plot_cryo.plot_eolis_timeseries(
                datacube=datacube,
                mass_balance=True,
                glacier_area=gdir.get("rgi_area_km2", None),
            ).opts(title="Monthly Cumulative Specific Mass Balance (CryoSat)")

            fig_eo_smb = self.plot_cryo.plot_eolis_smb(
                datacube=datacube,
                ref_year=year,
                years=None,
                cumulative=False,
                glacier_area=gdir.get("rgi_area_km2", None),
            ).opts(title="Cumulative Specific Mass Balance (CryoSat)")
            figures = [
                pn.pane.HoloViews(fig_eo_elevation),
                pn.pane.HoloViews(fig_eo_smb),
            ]

        return figures

    def plot_shapefile(self, shapefile, **kwargs) -> gv.Polygons:
        """Plot a shapefile.

        Parameters
        ----------
        shapefile : geopandas.GeoDataFrame
            Must contain polygon geometry.

        **kwargs
            Extra arguments for plotting Polygons. View
            ``gv.help(gv.Polygons)`` for all styling options.
        """
        plot = gv.Polygons(shapefile).opts(**kwargs)

        return plot

    @pn.cache
    def plot_region(self, shapefile, glacier_data, region_id: int) -> hv.Overlay:
        """Plot a region with all its glaciers.

        Parameters
        ----------
        shapefile : geopandas.GeoDataFrame
            Glacier shapefile, which may contain more than one region.
        glacier_data: geopandas.GeoDataFrame
            Glacier geometry for a glacier of interest.
        region_id : int
            RGI region ID of the region of interest.

        Returns
        -------
        hv.Overlay
            Interactive figure of all glaciers in a region.
        """

        mask = shapefile.O1Region == f"{int(region_id)}"  # single digit string

        overlay = (
            self.plot_shapefile(
                shapefile[mask],
                fill_color=self.palette[0],
                line_color="black",
                line_width=1.0,
                fill_alpha=0.4,
                color_index=None,
                scalebar=True,  # otherwise won't appear in overlay
                # tools=[self.hover_tool, "tap"],
            )
            * gv.tile_sources.EsriWorldTopo()
            * self.plot_shapefile(
                glacier_data,
                fill_color=self.palette[1],
                line_color="black",
                line_width=0.3,
                fill_alpha=0.9,
                color_index=None,
            )
            # .opts(**self.defaults)
            # .opts(
            #     tools=[self.hover_tool],
            # )
        )

        return overlay

    def plot_selection_map(
        self, shapefile, rgi_id: str, region_name: str = ""
    ) -> hv.Layout:
        """Plot map showing the selected glacier.

        Parameters
        ----------
        data : dict
            Contains glacier data, shapefile, and optionally runoff
            data and observations.
        glacier_name : str, optional
            Name of glacier in subregion. Default empty string.

        Returns
        -------
        hv.Layout
            Dashboard showing a map of the subregion and runoff data.
        """
        try:
            glacier_data = shapefile[shapefile["RGIId"] == f"RGI60-{rgi_id[6:]}"]
            fig_glacier_highlight = self.plot_map.plot_region(
                shapefile=shapefile, glacier_data=glacier_data, region_id=rgi_id[6:8]
            )
            if not region_name:
                region_name = rgi_id
            return fig_glacier_highlight.opts(
                # **self.defaults,
                scalebar=True,
                title=region_name,
                active_tools=["pan", "wheel_zoom"],
                backend_opts={"title.align": "center"},
                toolbar=None,
                show_frame=False,
                margin=0,
                border=0,
                # xlim=glacier_highlight.range("Latitude")
            )
        except Exception as e:
            return pn.pane.Markdown(f"""#Error in plot_selection_map: {e}""")
