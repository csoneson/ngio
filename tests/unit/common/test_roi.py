from ngio import PixelSize
from ngio.common import Dimensions, WorldCooROI
from ngio.ome_zarr_meta.ngio_specs import AxesMapper, Axis


def test_rois():
    roi = WorldCooROI(
        name="test",
        x=0.0,
        y=0.0,
        z=0.0,
        x_length=1.0,
        y_length=1.0,
        z_length=1.0,
        unit="micrometer",  # type: ignore
        other="other",  # type: ignore
    )

    assert roi.x == 0.0

    axes = [Axis(on_disk_name="x"), Axis(on_disk_name="y")]
    ax_mapper = AxesMapper(on_disk_axes=axes)
    dims = Dimensions(shape=(30, 30), axes_mapper=ax_mapper)

    pixel_size = PixelSize(x=1.0, y=1.0, z=1.0)
    raster_roi = roi.to_raster_coo(pixel_size, dims)

    assert raster_roi.x_slice() == slice(0, 1)
    assert raster_roi.y_slice() == slice(0, 1)
    assert raster_roi.z_slice() == slice(0, 1)
    assert roi.model_extra is not None
    assert roi.model_extra["other"] == "other"

    world_roi_2 = raster_roi.to_world_coo_roi(pixel_size)

    assert world_roi_2.x == 0.0
    assert world_roi_2.y == 0.0
    assert world_roi_2.z == 0.0
    assert world_roi_2.x_length == 1.0
    assert world_roi_2.y_length == 1.0
    assert world_roi_2.z_length == 1.0
