"""Fractal internal module for axes handling."""

from collections.abc import Collection
from enum import Enum
from logging import Logger
from typing import TypeVar

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from ngio.utils import NgioValidationError, NgioValueError

logger = Logger(__name__)

T = TypeVar("T")

################################################################################################
#
# Axis Types and Units
# We define a small set of axis types and units that can be used in the metadata.
# This axis types are more restrictive than the OME standard.
# We do that to simplify the data processing.
#
#################################################################################################


class AxisType(str, Enum):
    """Allowed axis types."""

    channel = "channel"
    time = "time"
    space = "space"


class SpaceUnits(str, Enum):
    """Allowed space units."""

    nanometer = "nanometer"
    nm = "nm"
    micrometer = "micrometer"
    um = "um"
    millimeter = "millimeter"
    mm = "mm"
    centimeter = "centimeter"
    cm = "cm"

    @classmethod
    def default(cls) -> "SpaceUnits":
        return SpaceUnits.um


class TimeUnits(str, Enum):
    """Allowed time units."""

    seconds = "seconds"
    s = "s"

    @classmethod
    def default(cls) -> "TimeUnits":
        return TimeUnits.s


class Axis(BaseModel):
    """Axis infos model."""

    on_disk_name: str
    unit: SpaceUnits | TimeUnits | None = None
    axis_type: AxisType | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)

    def implicit_type_cast(self, cast_type: AxisType) -> "Axis":
        if self.axis_type != cast_type:
            logger.warning(
                f"Axis {self.on_disk_name} has type {self.axis_type}. "
                f"Casting to {cast_type}."
            )
        new_axis = Axis(
            on_disk_name=self.on_disk_name, axis_type=cast_type, unit=self.unit
        )
        if cast_type == AxisType.time and not isinstance(self.unit, TimeUnits):
            logger.warning(
                f"Time axis {self.on_disk_name} has unit {self.unit}. "
                f"Casting to {TimeUnits.default()}."
            )
            new_axis = Axis(
                on_disk_name=self.on_disk_name,
                axis_type=AxisType.time,
                unit=TimeUnits.default(),
            )
        elif cast_type == AxisType.space and not isinstance(self.unit, SpaceUnits):
            logger.warning(
                f"Space axis {self.on_disk_name} has unit {self.unit}. "
                f"Casting to {SpaceUnits.default()}."
            )
            new_axis = Axis(
                on_disk_name=self.on_disk_name,
                axis_type=AxisType.space,
                unit=SpaceUnits.default(),
            )
        elif cast_type == AxisType.channel and self.unit is not None:
            logger.warning(
                f"Channel axis {self.on_disk_name} has unit {self.unit}. Removing unit."
            )
            new_axis = Axis(
                on_disk_name=self.on_disk_name,
                axis_type=AxisType.channel,
                unit=None,
            )
        return new_axis

    def canonical_axis_cast(self, canonical_name: str) -> "Axis":
        """Cast the implicit axis to the correct type."""
        match canonical_name:
            case "t":
                if self.axis_type != AxisType.time or not isinstance(
                    self.unit, TimeUnits
                ):
                    return self.implicit_type_cast(AxisType.time)
            case "c":
                if self.axis_type != AxisType.channel or self.unit is not None:
                    return self.implicit_type_cast(AxisType.channel)
            case "z" | "y" | "x":
                if self.axis_type != AxisType.space or not isinstance(
                    self.unit, SpaceUnits
                ):
                    return self.implicit_type_cast(AxisType.space)
        return self


################################################################################################
#
# Axes Handling
# We define a unique mapping to match the axes on disk to the canonical axes.
# The canonical axes are the ones that are used consistently in the NGIO internal API.
# The canonical axes ordered are: t, c, z, y, x.
#
#################################################################################################


def canonical_axes_order() -> tuple[str, str, str, str, str]:
    """Get the canonical axes order."""
    return "t", "c", "z", "y", "x"


class AxesSetup(BaseModel):
    """Axes setup model.

    This model is used to map the on disk axes to the canonical OME-Zarr axes.
    """

    x: str = "x"
    y: str = "y"
    z: str = "z"
    c: str = "c"
    t: str = "t"
    others: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", frozen=True)


def _check_unique_names(axes: Collection[Axis]):
    """Check if all axes on disk have unique names."""
    names = [ax.on_disk_name for ax in axes]
    if len(set(names)) != len(names):
        duplicates = {item for item in names if names.count(item) > 1}
        raise NgioValidationError(
            f"All axes must be unique. But found duplicates axes {duplicates}"
        )


def _check_non_canonical_axes(axes_setup: AxesSetup, allow_non_canonical_axes: bool):
    """Check if all axes are known."""
    if not allow_non_canonical_axes and len(axes_setup.others) > 0:
        raise NgioValidationError(
            f"Unknown axes {axes_setup.others}. Please set "
            "`allow_non_canonical_axes=True` to ignore them"
        )


def _check_axes_validity(axes: Collection[Axis], axes_setup: AxesSetup):
    """Check if all axes are valid."""
    _axes_setup = axes_setup.model_dump(exclude={"others"})
    _all_known_axes = [*_axes_setup.values(), *axes_setup.others]
    for ax in axes:
        if ax.on_disk_name not in _all_known_axes:
            raise NgioValidationError(
                f"Invalid axis name '{ax.on_disk_name}'. "
                f"Please correct map `{ax.on_disk_name}` "
                f"using the AxesSetup model {axes_setup}"
            )


def _check_canonical_order(
    axes: Collection[Axis], axes_setup: AxesSetup, strict_canonical_order: bool
):
    """Check if the axes are in the canonical order."""
    if not strict_canonical_order:
        return
    _on_disk_names = [ax.on_disk_name for ax in axes]
    _canonical_order = []
    for name in canonical_axes_order():
        mapped_name = getattr(axes_setup, name)
        if mapped_name in _on_disk_names:
            _canonical_order.append(mapped_name)

    if _on_disk_names != _canonical_order:
        raise NgioValidationError(
            f"Invalid axes order. The axes must be in the canonical order. "
            f"Expected {_canonical_order}, but found {_on_disk_names}"
        )


def validate_axes(
    axes: Collection[Axis],
    axes_setup: AxesSetup,
    allow_non_canonical_axes: bool = False,
    strict_canonical_order: bool = False,
) -> None:
    """Validate the axes."""
    if allow_non_canonical_axes and strict_canonical_order:
        raise NgioValidationError(
            "`allow_non_canonical_axes` and"
            "`strict_canonical_order` cannot be true at the same time."
            "If non canonical axes are allowed, the order cannot be checked."
        )
    _check_unique_names(axes=axes)
    _check_non_canonical_axes(
        axes_setup=axes_setup, allow_non_canonical_axes=allow_non_canonical_axes
    )
    _check_axes_validity(axes=axes, axes_setup=axes_setup)
    _check_canonical_order(
        axes=axes, axes_setup=axes_setup, strict_canonical_order=strict_canonical_order
    )


class AxesTransformation(BaseModel):
    pass


class AxesTranspose(AxesTransformation):
    axes: tuple[int, ...]


class AxesExpand(AxesTransformation):
    axes: tuple[int, ...]


class AxesSqueeze(AxesTransformation):
    axes: tuple[int, ...]


class AxesMapper:
    """Map on disk axes to canonical axes.

    This class is used to map the on disk axes to the canonical axes.

    """

    def __init__(
        self,
        # spec dictated args
        on_disk_axes: Collection[Axis],
        # user defined args
        axes_setup: AxesSetup | None = None,
        allow_non_canonical_axes: bool = False,
        strict_canonical_order: bool = False,
    ):
        """Create a new AxesMapper object.

        Args:
            on_disk_axes (list[Axis]): The axes on disk.
            axes_setup (AxesSetup, optional): The axis setup. Defaults to None.
            allow_non_canonical_axes (bool, optional): Allow non canonical axes.
            strict_canonical_order (bool, optional): Check if the axes are in the
                canonical order. Defaults to False.
        """
        axes_setup = axes_setup if axes_setup is not None else AxesSetup()

        validate_axes(
            axes=on_disk_axes,
            axes_setup=axes_setup,
            allow_non_canonical_axes=allow_non_canonical_axes,
            strict_canonical_order=strict_canonical_order,
        )

        self._allow_non_canonical_axes = allow_non_canonical_axes
        self._strict_canonical_order = strict_canonical_order

        self._canonical_order = canonical_axes_order()
        self._extended_canonical_order = [*axes_setup.others, *self._canonical_order]

        self._on_disk_axes = on_disk_axes
        self._axes_setup = axes_setup

        self._name_mapping = self._compute_name_mapping()
        self._index_mapping = self._compute_index_mapping()

        # Validate the axes type and cast them if necessary
        # This needs to be done after the name mapping is computed
        self.validate_axex_type()

    def _compute_name_mapping(self):
        """Compute the name mapping.

        The name mapping is a dictionary with keys the canonical axes names
        and values the on disk axes names.
        """
        _name_mapping = {}
        axis_setup_dict = self._axes_setup.model_dump(exclude={"others"})
        _on_disk_names = self.on_disk_axes_names
        for canonical_key, on_disk_value in axis_setup_dict.items():
            if on_disk_value in _on_disk_names:
                _name_mapping[canonical_key] = on_disk_value
            else:
                _name_mapping[canonical_key] = None

        for on_disk_name in _on_disk_names:
            if on_disk_name not in _name_mapping.keys():
                _name_mapping[on_disk_name] = on_disk_name
        return _name_mapping

    def _compute_index_mapping(self):
        """Compute the index mapping.

        The index mapping is a dictionary with keys the canonical axes names
        and values the on disk axes index.
        """
        _index_mapping = {}
        for canonical_key, on_disk_value in self._name_mapping.items():
            if on_disk_value is not None:
                _index_mapping[canonical_key] = self.on_disk_axes_names.index(
                    on_disk_value
                )
            else:
                _index_mapping[canonical_key] = None
        return _index_mapping

    @property
    def on_disk_axes(self) -> list[Axis]:
        return list(self._on_disk_axes)

    @property
    def on_disk_axes_names(self) -> list[str]:
        return [ax.on_disk_name for ax in self._on_disk_axes]

    def get_index(self, name: str) -> int | None:
        """Get the index of the axis by name."""
        if name not in self._index_mapping.keys():
            raise NgioValueError(
                f"Invalid axis name '{name}'. "
                f"Possible values are {self._index_mapping.keys()}"
            )
        return self._index_mapping[name]

    def get_axis(self, name: str) -> Axis | None:
        """Get the axis object by name."""
        index = self.get_index(name)
        if index is None:
            return None
        return self.on_disk_axes[index]

    def validate_axex_type(self):
        """Validate the axes type.

        If the axes type is not correct, a warning is issued.
        and the axis is implicitly cast to the correct type.
        """
        new_axes = []
        for axes in self.on_disk_axes:
            for name in self._canonical_order:
                if axes == self.get_axis(name):
                    new_axes.append(axes.canonical_axis_cast(name))
                    break
            else:
                new_axes.append(axes)
        self._on_disk_axes = new_axes

    def _change_order(
        self, names: Collection[str]
    ) -> tuple[tuple[int, ...], tuple[int, ...]]:
        unique_names = set()
        for name in names:
            if name not in self._index_mapping.keys():
                raise NgioValueError(
                    f"Invalid axis name '{name}'. "
                    f"Possible values are {self._index_mapping.keys()}"
                )
            _unique_name = self._name_mapping.get(name)
            if _unique_name is None:
                continue
            if _unique_name in unique_names:
                raise NgioValueError(
                    f"Duplicate axis name, two or more '{_unique_name}' were found. "
                    f"Please provide unique names."
                )
            unique_names.add(_unique_name)

        if len(self.on_disk_axes_names) > len(unique_names):
            missing_names = set(self.on_disk_axes_names) - unique_names
            raise NgioValueError(
                f"Some axes where not queried. "
                f"Please provide the following missing axes {missing_names}"
            )
        _indices, _insert = [], []
        for i, name in enumerate(names):
            _index = self._index_mapping[name]
            if _index is None:
                _insert.append(i)
            else:
                _indices.append(self._index_mapping[name])
        return tuple(_indices), tuple(_insert)

    def to_order(self, names: Collection[str]) -> tuple[AxesTransformation, ...]:
        """Get the new order of the axes."""
        _indices, _insert = self._change_order(names)
        return AxesTranspose(axes=_indices), AxesExpand(axes=_insert)

    def from_order(self, names: Collection[str]) -> tuple[AxesTransformation, ...]:
        """Get the new order of the axes."""
        _indices, _insert = self._change_order(names)
        # Inverse transpose is just the transpose with the inverse indices
        _reverse_indices = tuple(np.argsort(_indices))
        return AxesSqueeze(axes=_insert), AxesTranspose(axes=_reverse_indices)

    def to_canonical(self) -> tuple[AxesTransformation, ...]:
        """Get the new order of the axes."""
        return self.to_order(self._extended_canonical_order)

    def from_canonical(self) -> tuple[AxesTransformation, ...]:
        """Get the new order of the axes."""
        return self.from_order(self._extended_canonical_order)


def transform_array(
    array: np.ndarray, operations: tuple[AxesTransformation, ...]
) -> np.ndarray:
    for operation in operations:
        if isinstance(operation, AxesTranspose):
            array = np.transpose(array, operation.axes)
        elif isinstance(operation, AxesExpand):
            array = np.expand_dims(array, axis=operation.axes)
        elif isinstance(operation, AxesSqueeze):
            array = np.squeeze(array, axis=operation.axes)
        else:
            raise ValueError(f"Unknown operation {operation}")
    return array


def transform_list(
    input_list: list[T], default: T, operations: tuple[AxesTransformation, ...]
) -> list[T]:
    if isinstance(input_list, tuple):
        input_list = list(input_list)

    for operation in operations:
        if isinstance(operation, AxesTranspose):
            input_list = [input_list[i] for i in operation.axes]

        if isinstance(operation, AxesExpand):
            for ax in operation.axes:
                input_list.insert(ax, default)
        elif isinstance(operation, AxesSqueeze):
            for offset, ax in enumerate(operation.axes):
                input_list.pop(ax - offset)

    return input_list
