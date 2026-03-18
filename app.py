import panel as pn
from dtcg.api.external.call import StreamDatacube

import controller
import plotting
import wrangler

pn.extension("notifications")
pn.extension(design="material", sizing_mode="stretch_width")


def app():

    data_cache = wrangler.GlacierDataCache()
    plotter = plotting.GlacierPlotter()

    streamer = StreamDatacube(
        server="https://cluster.klima.uni-bremen.de/~dtcg/datacubes_case_study_regions/v2026.2/L1_and_L2/"
    )
    dashboard = controller.Dashboard(
        data_cache=data_cache, plotter=plotter, streamer=streamer
    )

    template = dashboard.build_dashboard()
    return template.servable()


app()
