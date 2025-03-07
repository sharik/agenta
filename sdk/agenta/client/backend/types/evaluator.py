# This file was auto-generated by Fern from our API Definition.

from ..core.pydantic_utilities import UniversalBaseModel
import typing
from ..core.pydantic_utilities import IS_PYDANTIC_V2
import pydantic


class Evaluator(UniversalBaseModel):
    name: str
    key: str
    direct_use: bool
    settings_template: typing.Dict[str, typing.Optional[typing.Any]]
    description: typing.Optional[str] = None
    oss: typing.Optional[bool] = None
    requires_llm_api_keys: typing.Optional[bool] = None
    tags: typing.List[str]

    if IS_PYDANTIC_V2:
        model_config: typing.ClassVar[pydantic.ConfigDict] = pydantic.ConfigDict(
            extra="allow", frozen=True
        )  # type: ignore # Pydantic v2
    else:

        class Config:
            frozen = True
            smart_union = True
            extra = pydantic.Extra.allow
