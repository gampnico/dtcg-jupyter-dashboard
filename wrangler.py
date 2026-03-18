import json
from pathlib import Path
from typing import Dict, Optional

import geopandas as gpd
import numpy as np
import xarray as xr


class GlacierDataCache:
    """Handle all data loading and caching."""

    def __init__(self, cache_path: str = "./static/data/l2_precompute/"):
        self.cache_path = Path(cache_path)
        self._glacier_cache: Dict[str, dict] = {}  # Local memory cache
        self._glacier_index: Optional[dict] = None

    def get_glacier_index(self) -> dict:
        """Get glacier_index."""
        if self._glacier_index is None:
            """TODO: This isn't scalable for multiple regions.

            Restructure so the region name is loaded dynamically in
            controller when "_on_region_change" is triggered. Ideally
            the glacier index should be called from
            `RGI-XX/glacier_index.json` rather than the current "global"
            glacier_index.json.
            """
            metadata = self.get_cached_glacier_index(cache=self.cache_path)
            regions = {"Central Europe", "Iceland"}
            glacier_hash = {}

            def sort_rgi(word):
                """Ensure glaciers are sorted alphabetically, with RGIs at the end."""
                if not word[0][0:3] == "RGI":
                    return word[0]
                else:
                    return f"zzz{word}"

            for name in regions:
                glacier_hash[name] = {}
                for k, v in metadata[name].items():
                    glacier_hash[name].update({v["Name"]: k})
                    glacier_hash[name] = dict(
                        sorted(glacier_hash[name].items(), key=sort_rgi)
                    )

            self._glacier_index = dict(sorted(glacier_hash.items()))

        return self._glacier_index

    async def get_glacier_data(self, rgi_id: str) -> dict:
        """Get data for a single glacier."""

        # Check if already cached
        if rgi_id not in self._glacier_cache:
            data = self.get_cached_data(rgi_id=rgi_id)
            self._glacier_cache[rgi_id] = data
        return self._glacier_cache[rgi_id]

    def get_cached_data(self, rgi_id: str) -> dict:
        """Get precomputed data for a single glacier.

        Parameters
        ----------
        rgi_id : str
            Glacier RGI ID.

        Returns
        -------
        dict
            Cached glacier dataset containing minimal GlacierDirectory
            data, datacube, time series for specific mass balance and
            runoff, and glacier outline. Unavailable datasets default
            to a ``NoneType`` object.
        """
        cached_data = self.get_cached_datasets(rgi_id=rgi_id, cache=self.cache_path)
        data = {
            "gdir": cached_data.get("gdir", None),
            "eolis": cached_data.get("eolis", None),
            "smb": cached_data.get("smb", None),
            "runoff_data": cached_data.get("runoff", None),
            "outlines": cached_data.get("outlines", None),
        }

        return data

    def get_cached_datasets(
        self, rgi_id: str, cache="./static/data/l2_precompute/"
    ) -> dict:

        if isinstance(cache, str):
            cache = Path(cache)
        cache_path = cache / rgi_id
        gdir = self.get_cached_gdir_data(cache_path=cache_path)
        smb = self.get_cached_smb_data(cache_path=cache_path)
        runoff = {}
        for key in [
            "Daily_Hugonnet_2000_2020",
            "Daily_Cryosat_2011_2020",
            "SfcDaily_Cryosat_2011_2020",
        ]:
            runoff[key] = self.get_cached_runoff_data(cache_path=cache_path, suffix=key)
        eolis = self.get_cached_eolis_data(cache_path=cache_path)
        outlines = self.get_cached_outline_data(cache_path=cache_path)

        cached_data = {
            "gdir": gdir,
            "smb": smb,
            "runoff": runoff,
            "eolis": eolis,
            "outlines": outlines,
        }

        return cached_data

    def get_cached_gdir_data(self, cache_path: Path) -> dict:

        try:
            with open(cache_path / "gdir.json", mode="r", encoding="utf-8") as file:
                raw = file.read()
                gdir = dict(json.loads(raw))
        except FileNotFoundError:
            return None
        return gdir

    def get_cached_smb_data(self, cache_path: Path) -> np.ndarray:
        try:
            smb = np.load(cache_path / "smb.npz")
        except FileNotFoundError:
            return None

        return smb

    def get_cached_runoff_data(
        self, cache_path: Path, suffix="Daily_Hugonnet_2000_2020"
    ) -> dict:
        try:
            runoff = xr.open_dataarray(cache_path / f"runoff_{suffix}.nc")
        except FileNotFoundError:
            return None

        runoff_data = {"monthly_runoff": runoff}
        return runoff_data

    def get_cached_eolis_data(self, cache_path: Path) -> xr.DataArray:
        try:
            eolis_data = xr.open_dataset(cache_path / "eolis.nc")
        except FileNotFoundError:
            return None
        return eolis_data

    def get_cached_glacier_index(
        self, index="glacier_index", cache="./static/data/l2_precompute/"
    ):
        if isinstance(cache, str):
            cache = Path(cache)
        cache_path = cache / f"{index}.json"
        with open(cache_path, mode="r", encoding="utf-8") as file:
            raw = file.read()
            glacier_index = dict(json.loads(raw))

        return glacier_index

    def get_cached_outline_data(self, cache_path: Path) -> gpd.GeoDataFrame:
        """Get glacier outlines.

        This is identical to ``gdir.read_shapefile``, so the CRS should
        later be converted to EPSG:4236"""
        try:
            glacier_outlines = gpd.read_feather(cache_path / "outlines.shp")
        except FileNotFoundError:
            return None

        return glacier_outlines

    def get_cached_region_outlines(
        self,
        region_id: int,
        file_name="glacier_outlines.shp",
    ) -> gpd.GeoDataFrame:
        """Get subregion domain outlines.

        Parameters
        ----------
        region_id : int
            O1 region ID number.
        file_name : str
            Shapefile name.

        """
        # region_id = int(rgi_id[6:8])
        regions = {"Central Europe": 11, "Iceland": 6}
        try:
            shapefile_path = Path(
                self.cache_path
                / f"RGI60-{str(regions[region_id]).zfill(2)}/{file_name}"
            )
            shapefile = gpd.read_feather(shapefile_path)
        except FileNotFoundError:
            return None

        return shapefile
