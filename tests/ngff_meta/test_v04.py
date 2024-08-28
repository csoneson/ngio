import json


class TestOMEZarrHandlerV04:
    def test_basic_workflow(self, ome_zarr_image_v04_path):
        from ngio.io import read_group_attrs
        from ngio.ngff_meta import get_ngff_image_meta_handler

        handler = get_ngff_image_meta_handler(
            zarr_path=ome_zarr_image_v04_path, meta_mode="image"
        )

        meta = handler.load_meta()
        handler.write_meta(meta)

        with open("tests/data/meta_v04/base_ome_zarr_image_meta.json") as f:
            base_ome_zarr_meta = json.load(f)

        saved_meta = read_group_attrs(store=ome_zarr_image_v04_path, zarr_format=2)
        assert saved_meta == base_ome_zarr_meta

    def test_basic_workflow_with_cache(self, ome_zarr_image_v04_path):
        from ngio.io import read_group_attrs
        from ngio.ngff_meta import get_ngff_image_meta_handler

        handler = get_ngff_image_meta_handler(
            zarr_path=ome_zarr_image_v04_path, meta_mode="image", cache=True
        )

        meta = handler.load_meta()
        handler.write_meta(meta)

        with open("tests/data/meta_v04/base_ome_zarr_image_meta.json") as f:
            base_ome_zarr_meta = json.load(f)

        saved_meta = read_group_attrs(store=ome_zarr_image_v04_path, zarr_format=2)
        assert saved_meta == base_ome_zarr_meta
