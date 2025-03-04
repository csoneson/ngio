"""Implementation of the FeatureTableV1 class.

This class follows the roi_table specification at:
https://fractal-analytics-platform.github.io/fractal-tasks-core/tables/
"""

from typing import Literal

import pandas as pd
from pydantic import BaseModel

from ngio.tables._validators import validate_index_key
from ngio.tables.backends import ImplementedTableBackends
from ngio.utils import ZarrGroupHandler


class RegionMeta(BaseModel):
    """Metadata for the region."""

    path: str


class FeatureTableMeta(BaseModel):
    """Metadata for the ROI table."""

    fractal_table_version: Literal["1"] = "1"
    type: Literal["feature_table"] = "feature_table"
    backend: str | None = None
    region: RegionMeta | None = None
    instance_key: str = "label"


class FeatureTableV1:
    """Class to represent a feature table.

    This can be used to load any table that does not have
    a specific definition.
    """

    def __init__(
        self,
        dataframe: pd.DataFrame | None = None,
        reference_label: str | None = None,
    ) -> None:
        """Initialize the GenericTable."""
        if reference_label is None:
            self._meta = FeatureTableMeta()
        else:
            path = f"../labels/{reference_label}"
            self._meta = FeatureTableMeta(region=RegionMeta(path=path))

        self._reference_label = reference_label
        self._instance_key = "label"
        if dataframe is None:
            self._dataframe = None
        else:
            self._dataframe = validate_index_key(
                dataframe, self._instance_key, overwrite=True
            )
        self._table_backend = None

    @staticmethod
    def type() -> str:
        """Return the type of the table."""
        return "feature_table"

    @staticmethod
    def version() -> str:
        """The generic table does not have a version.

        Since does not follow a specific schema.
        """
        return "1"

    @property
    def backend_name(self) -> str | None:
        """Return the name of the backend."""
        if self._table_backend is None:
            return None
        return self._table_backend.backend_name()

    @property
    def dataframe(self) -> pd.DataFrame:
        """Return the table as a DataFrame."""
        if self._dataframe is None and self._table_backend is None:
            raise ValueError(
                "The table does not have a DataFrame in memory nor a backend."
            )

        if self._dataframe is None and self._table_backend is not None:
            self._dataframe = self._table_backend.load_as_dataframe()

        if self._dataframe is None:
            raise ValueError(
                "The table does not have a DataFrame in memory nor a backend."
            )
        return self._dataframe

    @dataframe.setter
    def dataframe(self, dataframe: pd.DataFrame) -> None:
        """Set the table as a DataFrame."""
        self._dataframe = dataframe

    @classmethod
    def _from_handler(
        cls, handler: ZarrGroupHandler, backend_name: str | None = None
    ) -> "FeatureTableV1":
        """Create a new ROI table from a Zarr group handler."""
        meta = FeatureTableMeta(**handler.load_attrs())
        instance_key = "label" if meta.instance_key is None else meta.instance_key
        if backend_name is None:
            backend = ImplementedTableBackends().get_backend(
                backend_name=meta.backend,
                group_handler=handler,
                index_key=instance_key,
                index_type="int",
            )
        else:
            backend = ImplementedTableBackends().get_backend(
                backend_name=backend_name,
                group_handler=handler,
                index_key=instance_key,
                index_type="int",
            )
            meta.backend = backend_name

        if not backend.implements_dataframe:
            raise ValueError("The backend does not implement the dataframe protocol.")

        table = cls()
        table._meta = meta
        table._table_backend = backend
        return table

    def _set_backend(
        self,
        handler: ZarrGroupHandler,
        backend_name: str | None = None,
    ) -> None:
        """Set the backend of the table."""
        instance_key = "label" if self._instance_key is None else self._instance_key
        backend = ImplementedTableBackends().get_backend(
            backend_name=backend_name,
            group_handler=handler,
            index_key=instance_key,
            index_type="int",
        )
        self._meta.backend = backend_name
        self._table_backend = backend

    def consolidate(self) -> None:
        """Write the current state of the table to the Zarr file."""
        if self._table_backend is None:
            raise ValueError(
                "No backend set for the table. "
                "Please add the table to a OME-Zarr Image before calling consolidate."
            )

        self._table_backend.write_from_dataframe(
            self.dataframe, metadata=self._meta.model_dump(exclude_none=True)
        )
