"""Module to handle the channel information in the metadata.

Stores the same information as the Omero section of the ngff 0.4 metadata.
"""

from collections.abc import Collection
from difflib import SequenceMatcher
from enum import Enum
from typing import Any, TypeVar

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator

################################################################################################
#
# Omero Section of the Metadata is used to store channel information and visualisation
# settings.
# This section is transitory and will be likely changed in the future.
#
#################################################################################################


class NgioColors(str, Enum):
    """Default colors for the channels."""

    dapi = "0000FF"
    hoechst = "0000FF"
    gfp = "00FF00"
    cy3 = "FFFF00"
    cy5 = "FF0000"
    brightfield = "808080"
    red = "FF0000"
    yellow = "FFFF00"
    magenta = "FF00FF"
    cyan = "00FFFF"
    gray = "808080"
    green = "00FF00"

    @staticmethod
    def semi_random_pick(channel_name: str | None = None) -> "NgioColors":
        """Try to fuzzy match the color to the channel name.

        - If a channel name is given will try to match the channel name to the color.
        - If name has the paatern 'channel_x' cyclic rotate over a list of colors
            [cyan, magenta, yellow, green]
        - If no channel name is given will return a random color.
        """
        available_colors = NgioColors._member_names_

        if channel_name is None:
            # Purely random color
            color_str = available_colors[np.random.randint(0, len(available_colors))]
            return NgioColors.__members__[color_str]

        if channel_name.startswith("channel_"):
            # Rotate over a list of colors
            defaults_colors = [
                NgioColors.cyan,
                NgioColors.magenta,
                NgioColors.yellow,
                NgioColors.green,
            ]

            try:
                index = int(channel_name.split("_")[-1]) % len(defaults_colors)
                return defaults_colors[index]
            except ValueError:
                # If the name of the channel is something like
                # channel_dapi this will fail an proceed to the
                # standard fuzzy match
                pass

        similarity = {}
        for color in available_colors:
            # try to match the color to the channel name
            similarity[color] = SequenceMatcher(None, channel_name, color).ratio()
        color_str = max(similarity, key=similarity.get)
        return NgioColors.__members__[color_str]


def valid_hex_color(v: str) -> bool:
    """Validate a hexadecimal color.

    Check that `color` is made of exactly six elements which are letters
    (a-f or A-F) or digits (0-9).
    If fail, raise a ValueError.

    Implementation source:
    https://github.com/fractal-analytics-platform/fractal-tasks-core/fractal_tasks_core/channels.py#L87
    Original authors:
     - Tommaso Comparin <tommaso.comparin@exact-lab.it>
    """
    if len(v) != 6:
        return False
    allowed_characters = "abcdefABCDEF0123456789"
    for character in v:
        if character not in allowed_characters:
            return False
    return True


class ChannelVisualisation(BaseModel):
    """Channel visualisation model.

    Contains the information about the visualisation of a channel.

    Attributes:
        color(str): The color of the channel in hexadecimal format or a color name.
        min(int | float): The minimum value of the channel.
        max(int | float): The maximum value of the channel.
        start(int | float): The start value of the channel.
        end(int | float): The end value of the channel.
        active(bool): Whether the channel is active.
    """

    color: str | NgioColors | None = Field(default=None, validate_default=True)
    min: int | float = 0
    max: int | float = 65535
    start: int | float = 0
    end: int | float = 65535
    active: bool = True
    model_config = ConfigDict(extra="allow", frozen=True)

    @field_validator("color", mode="after")
    @classmethod
    def validate_color(cls, value: str | NgioColors) -> str:
        """Color validator.

        There are three possible values to set a color:
         - A hexadecimal string.
         - A color name.
         - A NgioColors element.
        """
        if value is None:
            return NgioColors.semi_random_pick().value
        if isinstance(value, str) and valid_hex_color(value):
            return value
        elif isinstance(value, NgioColors):
            return value.value
        elif isinstance(value, str):
            value_lower = value.lower()
            return NgioColors.semi_random_pick(value_lower).value
        else:
            raise ValueError(f"Invalid color {value}.")

    @classmethod
    def default_init(
        cls,
        color: str | NgioColors | None = None,
        start: int | float | None = None,
        end: int | float | None = None,
        active: bool = True,
        data_type: Any = np.uint16,
    ) -> "ChannelVisualisation":
        """Create a ChannelVisualisation object with the default unit.

        Args:
            color(str): The color of the channel in hexadecimal format or a color name.
            start(int | float | None): The start value of the channel.
            end(int | float | None): The end value of the channel.
            data_type(Any): The data type of the channel.
            active(bool): Whether the channel should be shown by default.
        """
        for func in [np.iinfo, np.finfo]:
            try:
                min_value = func(data_type).min
                max_value = func(data_type).max
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"Invalid data type {data_type}.")

        start = start if start is not None else min_value
        end = end if end is not None else max_value
        return cls(
            color=color,
            min=min_value,
            max=max_value,
            start=start,
            end=end,
            active=active,
        )


def default_channel_name(index: int) -> str:
    """Return the default channel name."""
    return f"channel_{index}"


class Channel(BaseModel):
    """Information about a channel in the image.

    Attributes:
        label(str): The label of the channel.
        wavelength_id(str): The wavelength ID of the channel.
        extra_fields(dict): To reduce the api surface, extra fields are stored in the
            the channel attributes will be stored in the extra_fields attribute.
    """

    label: str
    wavelength_id: str | None = None
    channel_visualisation: ChannelVisualisation
    model_config = ConfigDict(extra="allow", frozen=True)

    @classmethod
    def default_init(
        cls,
        label: str,
        wavelength_id: str | None = None,
        color: str | NgioColors | None = None,
        start: int | float | None = None,
        end: int | float | None = None,
        active: bool = True,
        data_type: Any = np.uint16,
    ) -> "Channel":
        """Create a Channel object with the default unit.

        Args:
            label(str): The label of the channel.
            wavelength_id(str | None): The wavelength ID of the channel.
            color(str): The color of the channel in hexadecimal format or a color name.
                If None, the color will be picked based on the label.
            start(int | float | None): The start value of the channel.
            end(int | float | None): The end value of the channel.
            active(bool): Whether the channel should be shown by default.
            data_type(Any): The data type of the channel.
        """
        if color is None:
            # If no color is provided, try to pick a color based on the label
            # See the NgioColors.semi_random_pick method for more details.
            color = label

        channel_visualization = ChannelVisualisation.default_init(
            color=color, start=start, end=end, active=active, data_type=data_type
        )

        if wavelength_id is None:
            # TODO Evaluate if a better default value can be used
            wavelength_id = label

        return cls(
            label=label,
            wavelength_id=wavelength_id,
            channel_visualisation=channel_visualization,
        )


T = TypeVar("T")


def _check_elements(elements: Collection[T], expected_type: Any) -> Collection[T]:
    """Check that the elements are of the same type."""
    if len(elements) == 0:
        raise ValueError("At least one element must be provided.")

    for element in elements:
        if not isinstance(element, expected_type):
            raise ValueError(
                f"All elements must be of the same type {expected_type}. Got {element}."
            )

    return elements


def _check_unique(elements: Collection[T]) -> Collection[T]:
    """Check that the elements are unique."""
    if len(set(elements)) != len(elements):
        raise ValueError("All elements must be unique.")
    return elements


class ChannelsMeta(BaseModel):
    """Information about the channels in the image.

    This model is roughly equivalent to the Omero section of the ngff 0.4 metadata.

    Attributes:
        channels(list[Channel]): The list of channels in the image.
    """

    channels: list[Channel] = Field(default_factory=list)
    model_config = ConfigDict(extra="allow", frozen=True)

    @field_validator("channels", mode="after")
    def validate_channels(cls, value: list[Channel]) -> list[Channel]:
        """Check that the channels are unique."""
        _check_unique([ch.label for ch in value])
        return value

    @classmethod
    def default_init(
        cls,
        labels: Collection[str] | int,
        wavelength_id: Collection[str] | None = None,
        colors: Collection[str | NgioColors] | None = None,
        start: Collection[int | float] | int | float | None = None,
        end: Collection[int | float] | int | float | None = None,
        active: Collection[bool] | None = None,
        data_type: Any = np.uint16,
        **omero_kwargs: dict,
    ) -> "ChannelsMeta":
        """Create a ChannelsMeta object with the default unit.

        Args:
            labels(Collection[str] | int): The list of channels names in the image.
                If an integer is provided, the channels will be named "channel_i".
            wavelength_id(Collection[str] | None): The wavelength ID of the channel.
                If None, the wavelength ID will be the same as the channel name.
            colors(Collection[str, NgioColors] | None): The list of colors for the
                channels. If None, the colors will be random.
            start(Collection[int | float] | int | float | None): The start value of the
                channel. If None, the start value will be the minimum value of the
                data type.
            end(Collection[int | float] | int | float | None): The end value of the
                channel. If None, the end value will be the maximum value of the
                data type.
            data_type(Any): The data type of the channel. Will be used to set the
                min and max values of the channel.
            active (Collection[bool] | None):active(bool): Whether the channel should
                be shown by default.
            omero_kwargs(dict): Extra fields to store in the omero attributes.
        """
        if isinstance(labels, int):
            labels = [default_channel_name(i) for i in range(labels)]

        labels = _check_elements(labels, str)
        labels = _check_unique(labels)

        _wavelength_id: Collection[str | None] = [None] * len(labels)
        if isinstance(wavelength_id, Collection):
            _wavelength_id = _check_elements(wavelength_id, str)
            _wavelength_id = _check_unique(wavelength_id)

        _colors: Collection[str | NgioColors] = ["random"] * len(labels)
        if isinstance(colors, Collection):
            _colors = _check_elements(colors, str | NgioColors)

        _start: Collection[int | float | None] = [None] * len(labels)
        if isinstance(start, Collection):
            _start = _check_elements(start, (int, float))

        _end: Collection[int | float | None] = [None] * len(labels)
        if isinstance(end, Collection):
            _end = _check_elements(end, (int, float))

        _active: Collection[bool] = [True] * len(labels)
        if isinstance(active, Collection):
            _active = _check_elements(active, bool)

        channels = []
        for ch_name, w_id, color, s, e, a in zip(
            labels, _wavelength_id, _colors, _start, _end, _active, strict=True
        ):
            channels.append(
                Channel.default_init(
                    label=ch_name,
                    wavelength_id=w_id,
                    color=color,
                    start=s,
                    end=e,
                    active=a,
                    data_type=data_type,
                )
            )
        return cls(channels=channels, **omero_kwargs)
