# Copyright 2020 The Feast Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from datetime import timedelta

from feast import BigQuerySource
from feast.entity import Entity
from feast.feature import Feature
from feast.feature_view import FeatureView
from feast.infra.provider import _get_column_names
from feast.value_type import ValueType


def test_get_column_names_preserves_feature_ordering():
    entity = Entity("my-entity", description="My entity", value_type=ValueType.STRING)
    fv = FeatureView(
        name="my-fv",
        entities=["my-entity"],
        ttl=timedelta(days=1),
        batch_source=BigQuerySource(table="non-existent-mock"),
        features=[
            Feature(name="a", dtype=ValueType.STRING),
            Feature(name="b", dtype=ValueType.STRING),
            Feature(name="c", dtype=ValueType.STRING),
            Feature(name="d", dtype=ValueType.STRING),
            Feature(name="e", dtype=ValueType.STRING),
            Feature(name="f", dtype=ValueType.STRING),
            Feature(name="g", dtype=ValueType.STRING),
            Feature(name="h", dtype=ValueType.STRING),
            Feature(name="i", dtype=ValueType.STRING),
            Feature(name="j", dtype=ValueType.STRING),
        ],
    )

    _, feature_list, _, _ = _get_column_names(fv, [entity])
    assert feature_list == ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]
