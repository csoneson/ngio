"""A module for handling the Plate Collection in an OME-Zarr file."""

from ngio.images import OmeZarrContainer
from ngio.ome_zarr_meta import (
    NgioPlateMeta,
    NgioWellMeta,
    find_plate_meta_handler,
    find_well_meta_handler,
    get_plate_meta_handler,
    get_well_meta_handler,
)
from ngio.utils import (
    AccessModeLiteral,
    StoreOrGroup,
    ZarrGroupHandler,
)


# Mock lock class that does nothing
class MockLock:
    """A mock lock class that does nothing."""

    def __enter__(self):
        """Enter the lock."""
        pass

    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the lock."""
        pass


class OmeZarrWell:
    """A class to handle the Well Collection in an OME-Zarr file."""

    def __init__(self, group_handler: ZarrGroupHandler) -> None:
        """Initialize the LabelGroupHandler.

        Args:
            group_handler: The Zarr group handler that contains the Well.
        """
        self._group_handler = group_handler
        self._meta_handler = find_well_meta_handler(group_handler)

    @property
    def meta_handler(self):
        """Return the metadata handler."""
        return self._meta_handler

    @property
    def meta(self):
        """Return the metadata."""
        return self._meta_handler.meta

    def paths(self, acquisition: int | None = None) -> list[str]:
        """Return the images paths in the well.

        If acquisition is None, return all images paths in the well.
        Else, return the images paths in the well for the given acquisition.

        Args:
            acquisition (int | None): The acquisition id to filter the images.
        """
        return self.meta.paths(acquisition)


class OmeZarrPlate:
    """A class to handle the Plate Collection in an OME-Zarr file."""

    def __init__(self, group_handler: ZarrGroupHandler) -> None:
        """Initialize the LabelGroupHandler.

        Args:
            group_handler: The Zarr group handler that contains the Plate.
        """
        self._group_handler = group_handler
        self._meta_handler = find_plate_meta_handler(group_handler)

    @property
    def meta_handler(self):
        """Return the metadata handler."""
        return self._meta_handler

    @property
    def meta(self):
        """Return the metadata."""
        return self._meta_handler.meta

    @property
    def columns(self) -> list[str]:
        """Return the number of columns in the plate."""
        return self.meta.columns

    @property
    def rows(self) -> list[str]:
        """Return the number of rows in the plate."""
        return self.meta.rows

    @property
    def acquisitions_names(self) -> list[str | None]:
        """Return the acquisitions in the plate."""
        return self.meta.acquisitions_names

    @property
    def acquisitions_ids(self) -> list[int]:
        """Return the acquisitions ids in the plate."""
        return self.meta.acquisitions_ids

    @property
    def wells_paths(self) -> list[str]:
        """Return the wells paths in the plate."""
        return self.meta.wells_paths

    def get_well_path(self, row: str, column: int | str) -> str:
        """Return the well path in the plate."""
        return self.meta.get_well_path(row=row, column=column)

    def get_image_path(self, row: str, column: int | str, path: str) -> str:
        """Return the image path in the plate."""
        well = self.get_well(row, column)
        if path not in well.paths():
            raise ValueError(f"Image {path} does not exist in well {row}{column}")
        return f"{self.get_well_path(row, column)}/{path}"

    def get_well(self, row: str, column: int | str) -> OmeZarrWell:
        """Get a well from the plate.

        Args:
            row (str): The row of the well.
            column (int | str): The column of the well.

        Returns:
            OmeZarrWell: The well.
        """
        well_path = self.meta.get_well_path(row=row, column=column)
        group_handler = self._group_handler.derive_handler(well_path)
        return OmeZarrWell(group_handler)

    def get_wells(self) -> dict[str, OmeZarrWell]:
        """Get all wells in the plate."""
        wells = {}
        for well_path in self.wells_paths:
            group_handler = self._group_handler.derive_handler(well_path)
            well = OmeZarrWell(group_handler)
            wells[well_path] = well
        return wells

    def get_images(self, acquisition: int | None = None) -> list[OmeZarrContainer]:
        """Get all images in the plate.

        Args:
            acquisition: The acquisition id to filter the images.
        """
        images = []
        for well_path, well in self.get_wells().items():
            for img_path in well.paths(acquisition):
                full_path = f"{well_path}/{img_path}"
                img_group_handler = self._group_handler.derive_handler(full_path)
                images.append(OmeZarrContainer(img_group_handler))
        return images

    def get_well_images(
        self, row: str, column: str | int, acquisition: int | None = None
    ) -> list[OmeZarrContainer]:
        """Get all images in a well.

        Args:
            row: The row of the well.
            column: The column of the well.
            acquisition: The acquisition id to filter the images.
        """
        well_path = self.meta.get_well_path(row=row, column=column)
        group_handler = self._group_handler.derive_handler(well_path)
        well = OmeZarrWell(group_handler)

        images = []
        for path in well.paths(acquisition):
            image_path = f"{well_path}/{path}"
            group_handler = self._group_handler.derive_handler(image_path)
            images.append(OmeZarrContainer(group_handler))

        return images

    def _add_image(
        self,
        row: str,
        column: int | str,
        image_path: str,
        acquisition_id: int | None = None,
        acquisition_name: str | None = None,
        atomic: bool = False,
    ):
        """Add an image to an ome-zarr plate."""
        if atomic:
            plate_lock = self._group_handler.lock
        else:
            plate_lock = MockLock()

        with plate_lock:
            meta = self.meta
            meta = meta.add_well(row, column, acquisition_id, acquisition_name)
            self.meta_handler.write_meta(meta)
            self.meta_handler._group_handler.clean_cache()

        well_path = self.meta.get_well_path(row=row, column=column)
        group_handler = self._group_handler.derive_handler(well_path)

        if atomic:
            well_lock = group_handler.lock
        else:
            well_lock = MockLock()

        with well_lock:
            attrs = group_handler.load_attrs()
            if len(attrs) == 0:
                # Initialize the well metadata
                # if the group is empty
                well_meta = NgioWellMeta.default_init(
                    images_paths=[], acquisition_ids=None
                )
                meta_handler = get_well_meta_handler(group_handler, version="0.4")
            else:
                meta_handler = find_well_meta_handler(group_handler)
                well_meta = meta_handler.meta

            group_handler = self._group_handler.derive_handler(well_path)

            well_meta = well_meta.add_image(path=image_path, acquisition=acquisition_id)
            meta_handler.write_meta(well_meta)
            meta_handler._group_handler.clean_cache()

    def atomic_add_image(
        self,
        row: str,
        column: int | str,
        image_path: str,
        acquisition_id: int | None = None,
        acquisition_name: str | None = None,
    ):
        """Parallel safe version of add_image."""
        return self._add_image(
            row=row,
            column=column,
            image_path=image_path,
            acquisition_id=acquisition_id,
            acquisition_name=acquisition_name,
            atomic=True,
        )

    def add_image(
        self,
        row: str,
        column: int | str,
        image_path: str,
        acquisition_id: int | None = None,
        acquisition_name: str | None = None,
    ):
        """Add an image to an ome-zarr plate."""
        return self._add_image(
            row=row,
            column=column,
            image_path=image_path,
            acquisition_id=acquisition_id,
            acquisition_name=acquisition_name,
            atomic=False,
        )

    def _remove_well(
        self,
        row: str,
        column: int | str,
        atomic: bool = False,
    ):
        """Remove a well from an ome-zarr plate."""
        if atomic:
            plate_lock = self._group_handler.lock
        else:
            plate_lock = MockLock()

        with plate_lock:
            meta = self.meta
            meta = meta.remove_well(row, column)
            self.meta_handler.write_meta(meta)
            self.meta_handler._group_handler.clean_cache()

    def _remove_image(
        self,
        row: str,
        column: int | str,
        image_path: str,
        atomic: bool = False,
    ):
        """Remove an image from an ome-zarr plate."""
        well = self.get_well(row, column)

        if atomic:
            well_lock = well.meta_handler._group_handler.lock
        else:
            well_lock = MockLock()

        with well_lock:
            well_meta = well.meta
            well_meta = well_meta.remove_image(path=image_path)
            well.meta_handler.write_meta(well_meta)
            well.meta_handler._group_handler.clean_cache()
            if len(well_meta.paths()) == 0:
                self._remove_well(row, column, atomic=atomic)

    def atomic_remove_image(
        self,
        row: str,
        column: int | str,
        image_path: str,
    ):
        """Parallel safe version of remove_image."""
        return self._remove_image(
            row=row,
            column=column,
            image_path=image_path,
            atomic=True,
        )

    def remove_image(
        self,
        row: str,
        column: int | str,
        image_path: str,
    ):
        """Remove an image from an ome-zarr plate."""
        return self._remove_image(
            row=row,
            column=column,
            image_path=image_path,
            atomic=False,
        )


def open_omezarr_plate(
    store: StoreOrGroup,
    cache: bool = False,
    mode: AccessModeLiteral = "r+",
    parallel_safe: bool = True,
) -> OmeZarrPlate:
    """Open an OME-Zarr plate.

    Args:
        store (StoreOrGroup): The Zarr store or group that stores the plate.
        cache (bool): Whether to use a cache for the zarr group metadata.
        mode (AccessModeLiteral): The
            access mode for the image. Defaults to "r+".
        parallel_safe (bool): Whether the group handler is parallel safe.
    """
    group_handler = ZarrGroupHandler(
        store=store, cache=cache, mode=mode, parallel_safe=parallel_safe
    )
    return OmeZarrPlate(group_handler)


def create_empty_plate(
    store: StoreOrGroup,
    name: str,
    version: str = "0.4",
    cache: bool = False,
    overwrite: bool = False,
    parallel_safe: bool = True,
):
    """Initialize and create an empty OME-Zarr plate."""
    mode = "w" if overwrite else "w-"
    group_handler = ZarrGroupHandler(
        store=store, cache=cache, mode=mode, parallel_safe=parallel_safe
    )
    meta_handler = get_plate_meta_handler(group_handler, version=version)
    plate_meta = NgioPlateMeta.default_init(
        rows=[],
        columns=[],
        acquisitions_ids=None,
        acquisitions_names=None,
        name=name,
        version=version,
    )
    meta_handler.write_meta(plate_meta)
    return OmeZarrPlate(group_handler)
