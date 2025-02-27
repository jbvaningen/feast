from copy import deepcopy

import pandas as pd
import pytest

from feast import (
    BigQuerySource,
    Entity,
    Feature,
    FileSource,
    RedshiftSource,
    RepoConfig,
    SnowflakeSource,
    ValueType,
)
from feast.data_source import RequestSource
from feast.errors import (
    DataSourceNoNameException,
    RegistryInferenceFailure,
    SpecifiedFeaturesNotPresentError,
)
from feast.feature_view import FeatureView
from feast.inference import (
    update_data_sources_with_inferred_event_timestamp_col,
    update_entities_with_inferred_types_from_feature_views,
)
from feast.infra.offline_stores.contrib.spark_offline_store.spark_source import (
    SparkSource,
)
from feast.on_demand_feature_view import on_demand_feature_view
from tests.utils.data_source_utils import (
    prep_file_source,
    simple_bq_source_using_query_arg,
    simple_bq_source_using_table_arg,
)


def test_update_entities_with_inferred_types_from_feature_views(
    simple_dataset_1, simple_dataset_2
):
    with prep_file_source(
        df=simple_dataset_1, event_timestamp_column="ts_1"
    ) as file_source, prep_file_source(
        df=simple_dataset_2, event_timestamp_column="ts_1"
    ) as file_source_2:

        fv1 = FeatureView(
            name="fv1", entities=["id"], batch_source=file_source, ttl=None,
        )
        fv2 = FeatureView(
            name="fv2", entities=["id"], batch_source=file_source_2, ttl=None,
        )

        actual_1 = Entity(name="id", join_key="id_join_key")
        actual_2 = Entity(name="id", join_key="id_join_key")

        update_entities_with_inferred_types_from_feature_views(
            [actual_1], [fv1], RepoConfig(provider="local", project="test")
        )
        update_entities_with_inferred_types_from_feature_views(
            [actual_2], [fv2], RepoConfig(provider="local", project="test")
        )
        assert actual_1 == Entity(
            name="id", join_key="id_join_key", value_type=ValueType.INT64
        )
        assert actual_2 == Entity(
            name="id", join_key="id_join_key", value_type=ValueType.STRING
        )

        with pytest.raises(RegistryInferenceFailure):
            # two viable data types
            update_entities_with_inferred_types_from_feature_views(
                [Entity(name="id", join_key="id_join_key")],
                [fv1, fv2],
                RepoConfig(provider="local", project="test"),
            )


def test_infer_datasource_names_file():
    file_path = "path/to/test.csv"
    data_source = FileSource(path=file_path)
    assert data_source.name == file_path

    source_name = "my_name"
    data_source = FileSource(name=source_name, path=file_path)
    assert data_source.name == source_name


def test_infer_datasource_names_dwh():
    table = "project.table"
    dwh_classes = [BigQuerySource, RedshiftSource, SnowflakeSource, SparkSource]

    for dwh_class in dwh_classes:
        data_source = dwh_class(table=table)
        assert data_source.name == table

        source_name = "my_name"
        data_source_with_table = dwh_class(name=source_name, table=table)
        assert data_source_with_table.name == source_name
        data_source_with_query = dwh_class(
            name=source_name, query=f"SELECT * from {table}"
        )
        assert data_source_with_query.name == source_name

        # If we have a query and no name, throw an error
        if dwh_class == SparkSource:
            with pytest.raises(DataSourceNoNameException):
                print(f"Testing dwh {dwh_class}")
                data_source = dwh_class(query="test_query")
        else:
            data_source = dwh_class(query="test_query")
            assert data_source.name == ""


@pytest.mark.integration
def test_update_file_data_source_with_inferred_event_timestamp_col(simple_dataset_1):
    df_with_two_viable_timestamp_cols = simple_dataset_1.copy(deep=True)
    df_with_two_viable_timestamp_cols["ts_2"] = simple_dataset_1["ts_1"]

    with prep_file_source(df=simple_dataset_1) as file_source:
        data_sources = [
            file_source,
            simple_bq_source_using_table_arg(simple_dataset_1),
            simple_bq_source_using_query_arg(simple_dataset_1),
        ]
        update_data_sources_with_inferred_event_timestamp_col(
            data_sources, RepoConfig(provider="local", project="test")
        )
        actual_event_timestamp_cols = [
            source.timestamp_field for source in data_sources
        ]

        assert actual_event_timestamp_cols == ["ts_1", "ts_1", "ts_1"]

    with prep_file_source(df=df_with_two_viable_timestamp_cols) as file_source:
        with pytest.raises(RegistryInferenceFailure):
            # two viable timestamp_fields
            update_data_sources_with_inferred_event_timestamp_col(
                [file_source], RepoConfig(provider="local", project="test")
            )


@pytest.mark.integration
@pytest.mark.universal
def test_update_data_sources_with_inferred_event_timestamp_col(universal_data_sources):
    (_, _, data_sources) = universal_data_sources
    data_sources_copy = deepcopy(data_sources)

    # remove defined timestamp_field to allow for inference
    for data_source in data_sources_copy.values():
        data_source.timestamp_field = None
        data_source.event_timestamp_column = None

    update_data_sources_with_inferred_event_timestamp_col(
        data_sources_copy.values(), RepoConfig(provider="local", project="test"),
    )
    actual_event_timestamp_cols = [
        source.timestamp_field for source in data_sources_copy.values()
    ]

    assert actual_event_timestamp_cols == ["event_timestamp"] * len(
        data_sources_copy.values()
    )


def test_on_demand_features_type_inference():
    # Create Feature Views
    date_request = RequestSource(
        name="date_request", schema={"some_date": ValueType.UNIX_TIMESTAMP}
    )

    @on_demand_feature_view(
        sources={"date_request": date_request},
        features=[
            Feature("output", ValueType.UNIX_TIMESTAMP),
            Feature("string_output", ValueType.STRING),
        ],
    )
    def test_view(features_df: pd.DataFrame) -> pd.DataFrame:
        data = pd.DataFrame()
        data["output"] = features_df["some_date"]
        data["string_output"] = features_df["some_date"].astype(pd.StringDtype())
        return data

    test_view.infer_features()

    @on_demand_feature_view(
        sources={"date_request": date_request},
        features=[
            Feature("output", ValueType.UNIX_TIMESTAMP),
            Feature("object_output", ValueType.STRING),
        ],
    )
    def invalid_test_view(features_df: pd.DataFrame) -> pd.DataFrame:
        data = pd.DataFrame()
        data["output"] = features_df["some_date"]
        data["object_output"] = features_df["some_date"].astype(str)
        return data

    with pytest.raises(ValueError, match="Value with native type object"):
        invalid_test_view.infer_features()

    @on_demand_feature_view(
        sources={"date_request": date_request},
        features=[
            Feature("output", ValueType.UNIX_TIMESTAMP),
            Feature("missing", ValueType.STRING),
        ],
    )
    def test_view_with_missing_feature(features_df: pd.DataFrame) -> pd.DataFrame:
        data = pd.DataFrame()
        data["output"] = features_df["some_date"]
        return data

    with pytest.raises(SpecifiedFeaturesNotPresentError):
        test_view_with_missing_feature.infer_features()


def test_datasource_inference():
    # Create Feature Views
    date_request = RequestSource(
        name="date_request", schema={"some_date": ValueType.UNIX_TIMESTAMP}
    )

    @on_demand_feature_view(
        sources={"date_request": date_request},
        features=[
            Feature("output", ValueType.UNIX_TIMESTAMP),
            Feature("string_output", ValueType.STRING),
        ],
    )
    def test_view(features_df: pd.DataFrame) -> pd.DataFrame:
        data = pd.DataFrame()
        data["output"] = features_df["some_date"]
        data["string_output"] = features_df["some_date"].astype(pd.StringDtype())
        return data

    test_view.infer_features()

    @on_demand_feature_view(
        sources={"date_request": date_request},
        features=[
            Feature("output", ValueType.UNIX_TIMESTAMP),
            Feature("object_output", ValueType.STRING),
        ],
    )
    def invalid_test_view(features_df: pd.DataFrame) -> pd.DataFrame:
        data = pd.DataFrame()
        data["output"] = features_df["some_date"]
        data["object_output"] = features_df["some_date"].astype(str)
        return data

    with pytest.raises(ValueError, match="Value with native type object"):
        invalid_test_view.infer_features()

    @on_demand_feature_view(
        sources={"date_request": date_request},
        features=[
            Feature("output", ValueType.UNIX_TIMESTAMP),
            Feature("missing", ValueType.STRING),
        ],
    )
    def test_view_with_missing_feature(features_df: pd.DataFrame) -> pd.DataFrame:
        data = pd.DataFrame()
        data["output"] = features_df["some_date"]
        return data

    with pytest.raises(SpecifiedFeaturesNotPresentError):
        test_view_with_missing_feature.infer_features()
