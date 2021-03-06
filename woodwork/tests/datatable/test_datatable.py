import re

import numpy as np
import pandas as pd
import pytest

import woodwork as ww
from woodwork import DataColumn, DataTable
from woodwork.datatable import _check_unique_column_names
from woodwork.logical_types import (
    URL,
    Boolean,
    Categorical,
    CountryCode,
    Datetime,
    Double,
    EmailAddress,
    Filepath,
    FullName,
    Integer,
    IPAddress,
    LatLong,
    LogicalType,
    NaturalLanguage,
    Ordinal,
    PhoneNumber,
    SubRegionCode,
    Timedelta,
    ZIPCode
)
from woodwork.tests.testing_utils import (
    check_column_order,
    mi_between_cols,
    to_pandas,
    validate_subset_dt
)
from woodwork.utils import import_or_none

dd = import_or_none('dask.dataframe')
dask_delayed = import_or_none('dask.delayed')
ks = import_or_none('databricks.koalas')


def test_datatable_df_property(sample_df):
    dt = DataTable(sample_df)
    assert dt.df is sample_df
    pd.testing.assert_frame_equal(to_pandas(dt.df), to_pandas(sample_df))


def test_datatable_with_numeric_datetime_time_index(time_index_df):
    dt = DataTable(time_index_df, time_index='ints', logical_types={'ints': Datetime})

    error_msg = 'Time index column must contain datetime or numeric values'
    with pytest.raises(TypeError, match=error_msg):
        DataTable(time_index_df, name='datatable', time_index='strs', logical_types={'strs': Datetime})

    assert dt.time_index == 'ints'
    assert dt.to_dataframe()['ints'].dtype == 'datetime64[ns]'


def test_datatable_with_numeric_time_index(time_index_df):
    # Set a numeric time index on init
    dt = DataTable(time_index_df, time_index='ints')
    date_col = dt['ints']
    assert dt.time_index == 'ints'
    assert date_col.logical_type == Integer
    assert date_col.semantic_tags == {'time_index', 'numeric'}

    # Specify logical type for time index on init
    dt = DataTable(time_index_df, time_index='ints', logical_types={'ints': 'Double'})
    date_col = dt['ints']
    assert dt.time_index == 'ints'
    assert date_col.logical_type == Double
    assert date_col.semantic_tags == {'time_index', 'numeric'}

    # Change time index to normal datetime time index
    dt = dt.set_time_index('times')
    date_col = dt['ints']
    assert dt.time_index == 'times'
    assert date_col.logical_type == Double
    assert date_col.semantic_tags == {'numeric'}

    # Set numeric time index after init
    dt = DataTable(time_index_df, logical_types={'ints': 'Double'})
    dt = dt.set_time_index('ints')
    date_col = dt['ints']
    assert dt.time_index == 'ints'
    assert date_col.logical_type == Double
    assert date_col.semantic_tags == {'time_index', 'numeric'}


def test_datatable_adds_standard_semantic_tags(sample_df):
    dt = DataTable(sample_df,
                   name='datatable',
                   logical_types={
                       'id': Categorical,
                       'age': Integer,
                   })

    assert dt.semantic_tags['id'] == {'category'}
    assert dt.semantic_tags['age'] == {'numeric'}


def test_check_unique_column_names(sample_df):
    if ks and isinstance(sample_df, ks.DataFrame):
        pytest.skip("Koalas enforces unique column names")
    duplicate_cols_df = sample_df.copy()
    if dd and isinstance(sample_df, dd.DataFrame):
        duplicate_cols_df = dd.concat([duplicate_cols_df, duplicate_cols_df['age']], axis=1)
    else:
        duplicate_cols_df.insert(0, 'age', [18, 21, 65, 43], allow_duplicates=True)
    with pytest.raises(IndexError, match='Dataframe cannot contain duplicate columns names'):
        _check_unique_column_names(duplicate_cols_df)


def test_datatable_types(sample_df):
    new_dates = ["2019~01~01", "2019~01~02", "2019~01~03", "2019~01~04"]
    if dd and isinstance(sample_df, dd.DataFrame):
        sample_df['formatted_date'] = pd.Series(new_dates)
    else:
        sample_df['formatted_date'] = new_dates
    ymd_format = Datetime(datetime_format='%Y~%m~%d')
    dt = DataTable(sample_df, logical_types={'formatted_date': ymd_format})
    returned_types = dt.types
    assert isinstance(returned_types, pd.DataFrame)
    assert 'Physical Type' in returned_types.columns
    assert 'Logical Type' in returned_types.columns
    assert 'Semantic Tag(s)' in returned_types.columns
    assert returned_types.shape[1] == 3
    assert len(returned_types.index) == len(sample_df.columns)
    assert all([dc.logical_type in ww.type_system.registered_types or isinstance(dc.logical_type, LogicalType) for dc in dt.columns.values()])
    correct_logical_types = {
        'id': Integer,
        'full_name': NaturalLanguage,
        'email': NaturalLanguage,
        'phone_number': NaturalLanguage,
        'age': Integer,
        'signup_date': Datetime,
        'is_registered': Boolean,
        'formatted_date': ymd_format
    }
    correct_logical_types = pd.Series(list(correct_logical_types.values()),
                                      index=list(correct_logical_types.keys()))
    assert correct_logical_types.equals(returned_types['Logical Type'])
    for tag in returned_types['Semantic Tag(s)']:
        assert isinstance(tag, str)


def test_datatable_typing_info_with_col_names(sample_df):
    dt = DataTable(sample_df)
    typing_info_df = dt._get_typing_info(include_names_col=True)

    assert isinstance(typing_info_df, pd.DataFrame)
    assert 'Data Column' in typing_info_df.columns
    assert 'Physical Type' in typing_info_df.columns
    assert 'Logical Type' in typing_info_df.columns
    assert 'Semantic Tag(s)' in typing_info_df.columns
    assert typing_info_df.shape[1] == 4
    assert typing_info_df.iloc[:, 0].name == 'Data Column'

    assert len(typing_info_df.index) == len(sample_df.columns)
    assert all([dc.logical_type in LogicalType.__subclasses__() or isinstance(dc.logical_type, LogicalType) for dc in dt.columns.values()])
    correct_logical_types = {
        'id': Integer,
        'full_name': NaturalLanguage,
        'email': NaturalLanguage,
        'phone_number': NaturalLanguage,
        'age': Integer,
        'signup_date': Datetime,
        'is_registered': Boolean,
    }
    correct_logical_types = pd.Series(list(correct_logical_types.values()),
                                      index=list(correct_logical_types.keys()))
    assert correct_logical_types.equals(typing_info_df['Logical Type'])
    for tag in typing_info_df['Semantic Tag(s)']:
        assert isinstance(tag, str)

    correct_column_names = pd.Series(list(sample_df.columns),
                                     index=list(sample_df.columns))
    assert typing_info_df['Data Column'].equals(correct_column_names)


def test_datatable_head(sample_df):
    dt = DataTable(sample_df, index='id', logical_types={'email': 'EmailAddress'}, semantic_tags={'signup_date': 'birthdat'})

    head = dt.head()
    assert isinstance(head, pd.DataFrame)
    assert isinstance(head.columns, pd.MultiIndex)
    if dd and isinstance(sample_df, dd.DataFrame):
        assert len(head) == 2
    else:
        assert len(head) == 4

    for i in range(len(head.columns)):
        name, dtype, logical_type, tags = head.columns[i]
        dc = dt[name]

        # confirm the order is the same
        assert dt._dataframe.columns[i] == name

        # confirm the rest of the attributes match up
        assert dc.dtype == dtype
        assert dc.logical_type == logical_type
        assert str(list(dc.semantic_tags)) == tags

    shorter_head = dt.head(1)
    assert len(shorter_head) == 1
    assert head.columns.equals(shorter_head.columns)


def test_datatable_repr(small_df):
    dt = DataTable(small_df)

    dt_repr = repr(dt)
    expected_repr = '                         Physical Type Logical Type Semantic Tag(s)\nData Column                                                        \nsample_datetime_series  datetime64[ns]     Datetime              []'
    assert dt_repr == expected_repr

    dt_html_repr = dt._repr_html_()
    expected_repr = '<table border="1" class="dataframe">\n  <thead>\n    <tr style="text-align: right;">\n      <th></th>\n      <th>Physical Type</th>\n      <th>Logical Type</th>\n      <th>Semantic Tag(s)</th>\n    </tr>\n    <tr>\n      <th>Data Column</th>\n      <th></th>\n      <th></th>\n      <th></th>\n    </tr>\n  </thead>\n  <tbody>\n    <tr>\n      <th>sample_datetime_series</th>\n      <td>datetime64[ns]</td>\n      <td>Datetime</td>\n      <td>[]</td>\n    </tr>\n  </tbody>\n</table>'
    assert dt_html_repr == expected_repr


def test_datatable_repr_empty(empty_df):
    dt = DataTable(empty_df)
    assert repr(dt) == 'Empty DataTable'

    assert dt._repr_html_() == 'Empty DataTable'

    assert dt.head() == 'Empty DataTable'


def test_set_types_combined(sample_df):
    dt = DataTable(sample_df, index='id', time_index='signup_date')
    assert dt['signup_date'].semantic_tags == set(['time_index'])
    assert dt['signup_date'].logical_type == Datetime
    assert dt['age'].semantic_tags == set(['numeric'])
    assert dt['age'].logical_type == Integer
    assert dt['is_registered'].semantic_tags == set()
    assert dt['is_registered'].logical_type == Boolean
    assert dt['email'].logical_type == NaturalLanguage
    assert dt['phone_number'].logical_type == NaturalLanguage

    semantic_tags = {
        'signup_date': ['test1'],
        'age': [],
        'is_registered': 'test2'
    }

    logical_types = {
        'email': 'EmailAddress',
        'phone_number': PhoneNumber,
        'age': 'Double'
    }

    dt = dt.set_types(logical_types=logical_types, semantic_tags=semantic_tags)
    assert dt['signup_date'].semantic_tags == set(['test1', 'time_index'])
    assert dt['signup_date'].logical_type == Datetime
    assert dt['age'].semantic_tags == set(['numeric'])
    assert dt['age'].logical_type == Double
    assert dt['is_registered'].semantic_tags == set(['test2'])
    assert dt['is_registered'].logical_type == Boolean
    assert dt['email'].logical_type == EmailAddress
    assert dt['phone_number'].logical_type == PhoneNumber


def test_new_dt_from_columns(sample_df):
    dt = DataTable(sample_df, time_index='signup_date', index='id', name='dt_name')
    dt = dt.set_types(logical_types={
        'full_name': FullName,
        'email': EmailAddress,
        'phone_number': PhoneNumber,
        'age': Double,
        'signup_date': Datetime,
    })
    dt.set_types(semantic_tags={
        'full_name': ['new_tag', 'tag2'],
        'age': 'numeric',
    })
    empty_dt = dt._new_dt_from_cols([])
    assert len(empty_dt.columns) == 0

    just_index = dt._new_dt_from_cols(['id'])
    assert just_index.index == dt.index
    assert just_index.time_index is None
    validate_subset_dt(just_index, dt)

    just_time_index = dt._new_dt_from_cols(['signup_date'])
    assert just_time_index.time_index == dt.time_index
    assert just_time_index.index is None
    validate_subset_dt(just_time_index, dt)

    transfer_schema = dt._new_dt_from_cols(['phone_number'])
    assert transfer_schema.index is None
    assert transfer_schema.time_index is None
    validate_subset_dt(transfer_schema, dt)


def test_pop(sample_df):
    dt = DataTable(sample_df,
                   name='datatable',
                   logical_types={'age': Integer},
                   semantic_tags={'age': 'custom_tag'},
                   use_standard_tags=True)
    datacol = dt.pop('age')
    assert isinstance(datacol, DataColumn)
    assert 'custom_tag' in datacol.semantic_tags
    assert all(to_pandas(datacol.to_series()).values == [33, 25, 33, 57])
    assert datacol.logical_type == Integer

    assert 'age' not in dt.to_dataframe().columns
    assert 'age' not in dt.columns

    assert 'age' not in dt.logical_types.keys()
    assert 'age' not in dt.semantic_tags.keys()


def test_shape(categorical_df):
    dt = ww.DataTable(categorical_df)
    dt_shape = dt.shape
    df_shape = dt.to_dataframe().shape
    if dd and isinstance(categorical_df, dd.DataFrame):
        assert isinstance(dt.shape[0], dask_delayed.Delayed)
        dt_shape = (dt_shape[0].compute(), dt_shape[1])
        df_shape = (df_shape[0].compute(), df_shape[1])
    assert dt_shape == (10, 5)
    assert dt_shape == df_shape

    dt.pop('ints')
    dt_shape = dt.shape
    df_shape = dt.to_dataframe().shape
    if dd and isinstance(categorical_df, dd.DataFrame):
        assert isinstance(dt.shape[0], dask_delayed.Delayed)
        dt_shape = (dt_shape[0].compute(), dt_shape[1])
        df_shape = (df_shape[0].compute(), df_shape[1])
    assert dt_shape == (10, 4)
    assert dt_shape == df_shape


def test_select_invalid_inputs(sample_df):
    dt = DataTable(sample_df, time_index='signup_date', index='id', name='dt_name')
    dt = dt.set_types(logical_types={
        'full_name': FullName,
        'email': EmailAddress,
        'phone_number': PhoneNumber,
        'age': Double,
        'signup_date': Datetime,
    })
    dt = dt.set_types(semantic_tags={
        'full_name': ['new_tag', 'tag2'],
        'age': 'numeric',
    })

    err_msg = "Invalid selector used in include: 1 must be either a string or LogicalType"
    with pytest.raises(TypeError, match=err_msg):
        dt.select(['boolean', 'index', Double, 1])

    dt_empty = dt.select([])
    assert len(dt_empty.columns) == 0


def test_select_single_inputs(sample_df):
    dt = DataTable(sample_df, time_index='signup_date', index='id', name='dt_name')
    dt = dt.set_types(logical_types={
        'full_name': FullName,
        'email': EmailAddress,
        'phone_number': PhoneNumber,
        'signup_date': Datetime(datetime_format='%Y-%m-%d')
    })
    dt = dt.set_types(semantic_tags={
        'full_name': ['new_tag', 'tag2'],
        'age': 'numeric',
        'signup_date': 'date_of_birth'
    })

    dt_ltype_string = dt.select('full_name')
    assert len(dt_ltype_string.columns) == 1
    assert 'full_name' in dt_ltype_string.columns

    dt_ltype_obj = dt.select(Integer)
    assert len(dt_ltype_obj.columns) == 2
    assert 'age' in dt_ltype_obj.columns
    assert 'id' in dt_ltype_obj.columns

    dt_tag_string = dt.select('index')
    assert len(dt_tag_string.columns) == 1
    assert 'id' in dt_tag_string.columns

    dt_tag_instantiated = dt.select('Datetime')
    assert len(dt_tag_instantiated.columns) == 1
    assert 'signup_date' in dt_tag_instantiated.columns


def test_select_list_inputs(sample_df):
    dt = DataTable(sample_df, time_index='signup_date', index='id', name='dt_name')
    dt = dt.set_types(logical_types={
        'full_name': FullName,
        'email': EmailAddress,
        'phone_number': PhoneNumber,
        'signup_date': Datetime(datetime_format='%Y-%m-%d'),
    })
    dt = dt.set_types(semantic_tags={
        'full_name': ['new_tag', 'tag2'],
        'age': 'numeric',
        'signup_date': 'date_of_birth',
        'email': 'tag2',
        'is_registered': 'category'
    })

    dt_just_strings = dt.select(['FullName', 'index', 'tag2', 'boolean'])
    assert len(dt_just_strings.columns) == 4
    assert 'id' in dt_just_strings.columns
    assert 'full_name' in dt_just_strings.columns
    assert 'email' in dt_just_strings.columns
    assert 'is_registered' in dt_just_strings.columns

    dt_mixed_selectors = dt.select([FullName, 'index', 'time_index', Integer])
    assert len(dt_mixed_selectors.columns) == 4
    assert 'id' in dt_mixed_selectors.columns
    assert 'full_name' in dt_mixed_selectors.columns
    assert 'signup_date' in dt_mixed_selectors.columns
    assert 'age' in dt_mixed_selectors.columns

    dt_common_tags = dt.select(['category', 'numeric', Boolean, Datetime])
    assert len(dt_common_tags.columns) == 3
    assert 'is_registered' in dt_common_tags.columns
    assert 'age' in dt_common_tags.columns
    assert 'signup_date' in dt_common_tags.columns


def test_select_instantiated():
    ymd_format = Datetime(datetime_format='%Y~%m~%d')

    df = pd.DataFrame({
        'dates': ["2019/01/01", "2019/01/02", "2019/01/03"],
        'ymd': ["2019~01~01", "2019~01~02", "2019~01~03"],
    })
    dt = DataTable(df,
                   logical_types={'ymd': ymd_format,
                                  'dates': Datetime})

    dt = dt.select('Datetime')
    assert len(dt.columns) == 2

    err_msg = "Invalid selector used in include: Datetime cannot be instantiated"
    with pytest.raises(TypeError, match=err_msg):
        dt.select(ymd_format)


def test_select_maintain_order(sample_df):
    dt = DataTable(sample_df, logical_types={col_name: 'NaturalLanguage' for col_name in sample_df.columns})
    new_dt = dt.select('NaturalLanguage')

    check_column_order(dt, new_dt)


def test_filter_cols(sample_df):
    dt = DataTable(sample_df, time_index='signup_date', index='id', name='dt_name')

    filtered = dt._filter_cols(include='email', col_names=True)
    assert filtered == ['email']

    filtered_log_type_string = dt._filter_cols(include='NaturalLanguage')
    filtered_log_type = dt._filter_cols(include=NaturalLanguage)
    assert filtered_log_type == filtered_log_type_string

    filtered_semantic_tag = dt._filter_cols(include='numeric')
    assert filtered_semantic_tag == ['age']

    filtered_multiple = dt._filter_cols(include=['numeric'])
    expected = ['phone_number', 'age']
    for col in filtered_multiple:
        assert col in expected

    filtered_multiple_overlap = dt._filter_cols(include=['NaturalLanguage', 'email'], col_names=True)
    expected = ['full_name', 'phone_number', 'email']
    for col in filtered_multiple_overlap:
        assert col in expected


def test_datetime_inference_with_format_param():
    df = pd.DataFrame({
        'index': [0, 1, 2],
        'dates': ["2019/01/01", "2019/01/02", "2019/01/03"],
        'ymd_special': ["2019~01~01", "2019~01~02", "2019~01~03"],
        'mdy_special': pd.Series(['3~11~2000', '3~12~2000', '3~13~2000'], dtype='string'),
    })
    dt = DataTable(df,
                   name='dt_name',
                   logical_types={'ymd_special': Datetime(datetime_format='%Y~%m~%d'),
                                  'mdy_special': Datetime(datetime_format='%m~%d~%Y'),
                                  'dates': Datetime},
                   time_index='ymd_special')

    assert dt.time_index == 'ymd_special'
    assert dt['dates'].logical_type == Datetime
    assert isinstance(dt['ymd_special'].logical_type, Datetime)
    assert isinstance(dt['mdy_special'].logical_type, Datetime)

    dt = dt.set_time_index('mdy_special')
    assert dt.time_index == 'mdy_special'

    df = pd.DataFrame({
        'mdy_special': pd.Series(['3&11&2000', '3&12&2000', '3&13&2000'], dtype='string'),
    })
    dt = DataTable(df)

    dt = dt.set_types(logical_types={'mdy_special': Datetime(datetime_format='%m&%d&%Y')})
    dt.time_index = 'mdy_special'
    assert isinstance(dt['mdy_special'].logical_type, Datetime)
    assert dt.time_index == 'mdy_special'


def test_natural_language_inference_with_config_options():
    dataframe = pd.DataFrame({
        'index': [0, 1, 2],
        'values': ["0123456", "01234567", "012345"]
    })

    ww.config.set_option('natural_language_threshold', 5)
    dt = DataTable(dataframe, name='dt_name')
    assert dt.columns['values'].logical_type == NaturalLanguage
    ww.config.reset_option('natural_language_threshold')


def test_describe_dict(describe_df):
    dt = DataTable(describe_df, index='index_col')
    stats_dict = dt.describe_dict()
    index_order = ['physical_type',
                   'logical_type',
                   'semantic_tags',
                   'count',
                   'nunique',
                   'nan_count',
                   'mean',
                   'mode',
                   'std',
                   'min',
                   'first_quartile',
                   'second_quartile',
                   'third_quartile',
                   'max',
                   'num_true',
                   'num_false']
    stats_dict_to_df = pd.DataFrame(stats_dict).reindex(index_order)
    stats_df = dt.describe()
    pd.testing.assert_frame_equal(stats_df, stats_dict_to_df)


def test_describe_does_not_include_index(describe_df):
    dt = DataTable(describe_df, index='index_col')
    stats_df = dt.describe()
    assert 'index_col' not in stats_df.columns


def test_datatable_describe_method(describe_df):
    categorical_ltypes = [Categorical,
                          CountryCode,
                          Ordinal(order=('yellow', 'red', 'blue')),
                          SubRegionCode,
                          ZIPCode]
    boolean_ltypes = [Boolean]
    datetime_ltypes = [Datetime]
    formatted_datetime_ltypes = [Datetime(datetime_format='%Y~%m~%d')]
    timedelta_ltypes = [Timedelta]
    numeric_ltypes = [Double, Integer]
    natural_language_ltypes = [EmailAddress, Filepath, FullName, IPAddress,
                               PhoneNumber, URL]
    latlong_ltypes = [LatLong]

    expected_index = ['physical_type',
                      'logical_type',
                      'semantic_tags',
                      'count',
                      'nunique',
                      'nan_count',
                      'mean',
                      'mode',
                      'std',
                      'min',
                      'first_quartile',
                      'second_quartile',
                      'third_quartile',
                      'max',
                      'num_true',
                      'num_false']

    # Test categorical columns
    category_data = describe_df[['category_col']]
    if ks and isinstance(category_data, ks.DataFrame):
        expected_dtype = 'object'
    else:
        expected_dtype = 'category'

    for ltype in categorical_ltypes:
        expected_vals = pd.Series({
            'physical_type': expected_dtype,
            'logical_type': ltype,
            'semantic_tags': {'category', 'custom_tag'},
            'count': 7,
            'nunique': 3,
            'nan_count': 1,
            'mode': 'red'}, name='category_col')
        dt = DataTable(category_data, logical_types={'category_col': ltype}, semantic_tags={'category_col': 'custom_tag'})
        stats_df = dt.describe()
        assert isinstance(stats_df, pd.DataFrame)
        assert set(stats_df.columns) == {'category_col'}
        assert stats_df.index.tolist() == expected_index
        pd.testing.assert_series_equal(expected_vals, stats_df['category_col'].dropna())

    # Test boolean columns
    boolean_data = describe_df[['boolean_col']]
    if ks and isinstance(category_data, ks.DataFrame):
        expected_dtype = 'bool'
    else:
        expected_dtype = 'boolean'
    for ltype in boolean_ltypes:
        expected_vals = pd.Series({
            'physical_type': expected_dtype,
            'logical_type': ltype,
            'semantic_tags': {'custom_tag'},
            'count': 8,
            'nan_count': 0,
            'mode': True,
            'num_true': 5,
            'num_false': 3}, name='boolean_col')
        dt = DataTable(boolean_data, logical_types={'boolean_col': ltype}, semantic_tags={'boolean_col': 'custom_tag'})
        stats_df = dt.describe()
        assert isinstance(stats_df, pd.DataFrame)
        assert set(stats_df.columns) == {'boolean_col'}
        assert stats_df.index.tolist() == expected_index
        pd.testing.assert_series_equal(expected_vals, stats_df['boolean_col'].dropna())

    # Test datetime columns
    datetime_data = describe_df[['datetime_col']]
    for ltype in datetime_ltypes:
        expected_vals = pd.Series({
            'physical_type': ltype.pandas_dtype,
            'logical_type': ltype,
            'semantic_tags': {'custom_tag'},
            'count': 7,
            'nunique': 6,
            'nan_count': 1,
            'mean': pd.Timestamp('2020-01-19 09:25:42.857142784'),
            'mode': pd.Timestamp('2020-02-01 00:00:00'),
            'min': pd.Timestamp('2020-01-01 00:00:00'),
            'max': pd.Timestamp('2020-02-02 18:00:00')}, name='datetime_col')
        dt = DataTable(datetime_data, logical_types={'datetime_col': ltype}, semantic_tags={'datetime_col': 'custom_tag'})
        stats_df = dt.describe()
        assert isinstance(stats_df, pd.DataFrame)
        assert set(stats_df.columns) == {'datetime_col'}
        assert stats_df.index.tolist() == expected_index
        pd.testing.assert_series_equal(expected_vals, stats_df['datetime_col'].dropna())

    # Test formatted datetime columns
    formatted_datetime_data = describe_df[['formatted_datetime_col']]
    for ltype in formatted_datetime_ltypes:
        converted_to_datetime = pd.to_datetime(['2020-01-01',
                                                '2020-02-01',
                                                '2020-03-01',
                                                '2020-02-02',
                                                '2020-03-02',
                                                pd.NaT,
                                                '2020-02-01',
                                                '2020-01-02'])
        expected_vals = pd.Series({
            'physical_type': ltype.pandas_dtype,
            'logical_type': ltype,
            'semantic_tags': {'custom_tag'},
            'count': 7,
            'nunique': 6,
            'nan_count': 1,
            'mean': converted_to_datetime.mean(),
            'mode': pd.to_datetime('2020-02-01'),
            'min': converted_to_datetime.min(),
            'max': converted_to_datetime.max()}, name='formatted_datetime_col')
        dt = DataTable(formatted_datetime_data,
                       logical_types={'formatted_datetime_col': ltype},
                       semantic_tags={'formatted_datetime_col': 'custom_tag'})
        stats_df = dt.describe()
        assert isinstance(stats_df, pd.DataFrame)
        assert set(stats_df.columns) == {'formatted_datetime_col'}
        assert stats_df.index.tolist() == expected_index
        pd.testing.assert_series_equal(expected_vals, stats_df['formatted_datetime_col'].dropna())

    # Test timedelta columns - Skip for Koalas
    if not (ks and isinstance(describe_df, ks.DataFrame)):
        timedelta_data = describe_df['timedelta_col']
        for ltype in timedelta_ltypes:
            expected_vals = pd.Series({
                'physical_type': ltype.pandas_dtype,
                'logical_type': ltype,
                'semantic_tags': {'custom_tag'},
                'count': 7,
                'nan_count': 1,
                'mode': pd.Timedelta('31days')}, name='col')
            df = pd.DataFrame({'col': timedelta_data})
            dt = DataTable(df, logical_types={'col': ltype}, semantic_tags={'col': 'custom_tag'})
            stats_df = dt.describe()
            assert isinstance(stats_df, pd.DataFrame)
            assert set(stats_df.columns) == {'col'}
            assert stats_df.index.tolist() == expected_index
            pd.testing.assert_series_equal(expected_vals, stats_df['col'].dropna())

    # Test numeric columns
    numeric_data = describe_df[['numeric_col']]
    for ltype in numeric_ltypes:
        expected_vals = pd.Series({
            'physical_type': ltype.pandas_dtype,
            'logical_type': ltype,
            'semantic_tags': {'numeric', 'custom_tag'},
            'count': 7,
            'nunique': 6,
            'nan_count': 1,
            'mean': 20.857142857142858,
            'mode': 10,
            'std': 18.27957486220227,
            'min': 1,
            'first_quartile': 10,
            'second_quartile': 17,
            'third_quartile': 26,
            'max': 56}, name='numeric_col')
        dt = DataTable(numeric_data, logical_types={'numeric_col': ltype}, semantic_tags={'numeric_col': 'custom_tag'})
        stats_df = dt.describe()
        assert isinstance(stats_df, pd.DataFrame)
        assert set(stats_df.columns) == {'numeric_col'}
        assert stats_df.index.tolist() == expected_index
        pd.testing.assert_series_equal(expected_vals, stats_df['numeric_col'].dropna(), check_exact=False)

    # Test natural language columns
    natural_language_data = describe_df[['natural_language_col']]
    if ks and isinstance(category_data, ks.DataFrame):
        expected_dtype = 'object'
    else:
        expected_dtype = 'string'
    for ltype in natural_language_ltypes:
        expected_vals = pd.Series({
            'physical_type': expected_dtype,
            'logical_type': ltype,
            'semantic_tags': {'custom_tag'},
            'count': 7,
            'nan_count': 1,
            'mode': 'Duplicate sentence.'}, name='natural_language_col')
        dt = DataTable(natural_language_data,
                       logical_types={'natural_language_col': ltype},
                       semantic_tags={'natural_language_col': 'custom_tag'})
        stats_df = dt.describe()
        assert isinstance(stats_df, pd.DataFrame)
        assert set(stats_df.columns) == {'natural_language_col'}
        assert stats_df.index.tolist() == expected_index
        pd.testing.assert_series_equal(expected_vals, stats_df['natural_language_col'].dropna())

    # Test latlong columns
    latlong_data = describe_df[['latlong_col']]
    expected_dtype = 'object'
    for ltype in latlong_ltypes:
        mode = [0, 0] if ks and isinstance(describe_df, ks.DataFrame) else (0, 0)
        expected_vals = pd.Series({
            'physical_type': expected_dtype,
            'logical_type': ltype,
            'semantic_tags': {'custom_tag'},
            'count': 6,
            'nan_count': 2,
            'mode': mode}, name='latlong_col')
        dt = DataTable(latlong_data,
                       logical_types={'latlong_col': ltype},
                       semantic_tags={'latlong_col': 'custom_tag'})
        stats_df = dt.describe()
        assert isinstance(stats_df, pd.DataFrame)
        assert set(stats_df.columns) == {'latlong_col'}
        assert stats_df.index.tolist() == expected_index
        pd.testing.assert_series_equal(expected_vals, stats_df['latlong_col'].dropna())


def test_datatable_describe_with_improper_tags(describe_df):
    df = describe_df.copy()[['boolean_col', 'natural_language_col']]

    logical_types = {
        'boolean_col': Boolean,
        'natural_language_col': NaturalLanguage,
    }
    semantic_tags = {
        'boolean_col': 'category',
        'natural_language_col': 'numeric',
    }

    dt = DataTable(df, logical_types=logical_types, semantic_tags=semantic_tags)
    stats_df = dt.describe()

    # Make sure boolean stats were computed with improper 'category' tag
    assert stats_df['boolean_col']['logical_type'] == Boolean
    assert stats_df['boolean_col']['semantic_tags'] == {'category'}
    # Make sure numeric stats were not computed with improper 'numeric' tag
    assert stats_df['natural_language_col']['semantic_tags'] == {'numeric'}
    assert stats_df['natural_language_col'][['mean', 'std', 'min', 'max']].isnull().all()


def test_datatable_describe_with_no_semantic_tags(describe_df):
    df = describe_df.copy()[['category_col', 'numeric_col']]

    logical_types = {
        'category_col': Categorical,
        'numeric_col': Integer,
    }

    dt = DataTable(df, logical_types=logical_types, use_standard_tags=False)
    stats_df = dt.describe()
    assert dt['category_col'].semantic_tags == set()
    assert dt['numeric_col'].semantic_tags == set()

    # Make sure category stats were computed
    assert stats_df['category_col']['semantic_tags'] == set()
    assert stats_df['category_col']['nunique'] == 3
    # Make sure numeric stats were computed
    assert stats_df['numeric_col']['semantic_tags'] == set()
    np.testing.assert_almost_equal(stats_df['numeric_col']['mean'], 20.85714, 5)


def test_datatable_describe_with_include(sample_df):
    semantic_tags = {
        'full_name': 'tag1',
        'email': ['tag2'],
        'age': ['numeric', 'age']
    }
    dt = DataTable(sample_df, semantic_tags=semantic_tags)

    col_name_df = dt.describe(include=['full_name'])
    assert col_name_df.shape == (16, 1)
    assert 'full_name', 'email' in col_name_df.columns

    semantic_tags_df = dt.describe(['tag1', 'tag2'])
    assert 'full_name' in col_name_df.columns
    assert len(semantic_tags_df.columns) == 2

    logical_types_df = dt.describe([Datetime, Boolean])
    assert 'signup_date', 'is_registered' in logical_types_df.columns
    assert len(logical_types_df.columns) == 2

    multi_params_df = dt.describe(['age', 'tag1', Datetime])
    expected = ['full_name', 'age', 'signup_date']
    for col_name in expected:
        assert col_name in multi_params_df.columns
    multi_params_df['full_name'].equals(col_name_df['full_name'])
    multi_params_df['full_name'].equals(dt.describe()['full_name'])


def test_value_counts(categorical_df):
    logical_types = {
        'ints': Integer,
        'categories1': Categorical,
        'bools': Boolean,
        'categories2': Categorical,
        'categories3': Categorical,
    }
    dt = DataTable(categorical_df, logical_types=logical_types)
    val_cts = dt.value_counts()
    for col in dt.columns:
        if col in ['ints', 'bools']:
            assert col not in val_cts
        else:
            assert col in val_cts

    none_val = np.nan
    expected_cat1 = [{'value': 200, 'count': 4}, {'value': 100, 'count': 3}, {'value': 1, 'count': 2}, {'value': 3, 'count': 1}]
    # Koalas converts numeric categories to strings, so we need to update the expected values for this
    # Koalas will result in `None` instead of `np.nan` in categorical columns
    if ks and isinstance(categorical_df, ks.DataFrame):
        updated_results = []
        for items in expected_cat1:
            updated_results.append({k: (str(v) if k == 'value' else v) for k, v in items.items()})
        expected_cat1 = updated_results
        none_val = 'None'

    assert val_cts['categories1'] == expected_cat1
    assert val_cts['categories2'] == [{'value': none_val, 'count': 6}, {'value': 'test', 'count': 3}, {'value': 'test2', 'count': 1}]
    assert val_cts['categories3'] == [{'value': none_val, 'count': 7}, {'value': 'test', 'count': 3}]

    val_cts_descending = dt.value_counts(ascending=True)
    for col, vals in val_cts_descending.items():
        for i in range(len(vals)):
            assert vals[i]['count'] == val_cts[col][-i - 1]['count']

    val_cts_dropna = dt.value_counts(dropna=True)
    assert val_cts_dropna['categories3'] == [{'value': 'test', 'count': 3}]

    val_cts_2 = dt.value_counts(top_n=2)
    for col in val_cts_2:
        assert len(val_cts_2[col]) == 2


def test_datatable_replace_nans_for_mutual_info():
    df_nans = pd.DataFrame({
        'ints': pd.Series([2, pd.NA, 5, 2], dtype='Int64'),
        'floats': pd.Series([3.3, None, 2.3, 1.3]),
        'bools': pd.Series([True, None, True, False]),
        'int_to_cat_nan': pd.Series([1, np.nan, 3, 1], dtype='category'),
        'str': pd.Series(['test', np.nan, 'test2', 'test']),
        'str_no_nan': pd.Series(['test', 'test2', 'test2', 'test']),
        'dates': pd.Series(['2020-01-01', None, '2020-01-02', '2020-01-03'])
    })
    dt_nans = DataTable(df_nans)
    formatted_df = dt_nans._replace_nans_for_mutual_info(dt_nans.to_dataframe().copy())

    assert isinstance(formatted_df, pd.DataFrame)

    assert formatted_df['ints'].equals(pd.Series([2, 3, 5, 2], dtype='Int64'))
    assert formatted_df['floats'].equals(pd.Series([3.3, 2.3, 2.3, 1.3], dtype='float'))
    assert formatted_df['bools'].equals(pd.Series([True, True, True, False], dtype='category'))
    assert formatted_df['int_to_cat_nan'].equals(pd.Series([1, 1, 3, 1], dtype='category'))
    assert formatted_df['str'].equals(pd.Series(['test', 'test', 'test2', 'test'], dtype='category'))
    assert formatted_df['str_no_nan'].equals(pd.Series(['test', 'test2', 'test2', 'test'], dtype='category'))
    assert formatted_df['dates'].equals(pd.Series(['2020-01-01', '2020-01-02', '2020-01-02', '2020-01-03'], dtype='datetime64[ns]'))


def test_datatable_make_categorical_for_mutual_info():
    df = pd.DataFrame({
        'ints1': pd.Series([1, 2, 3, 2]),
        'ints2': pd.Series([1, 100, 1, 100]),
        'bools': pd.Series([True, False, True, False]),
        'categories': pd.Series(['test', 'test2', 'test2', 'test']),
        'dates': pd.Series(['2020-01-01', '2019-01-02', '2020-08-03', '1997-01-04'])
    })
    dt = DataTable(df)
    formatted_num_bins_df = dt._make_categorical_for_mutual_info(dt.to_dataframe().copy(), num_bins=4)

    assert isinstance(formatted_num_bins_df, pd.DataFrame)

    assert formatted_num_bins_df['ints1'].equals(pd.Series([0, 1, 3, 1], dtype='int8'))
    assert formatted_num_bins_df['ints2'].equals(pd.Series([0, 1, 0, 1], dtype='int8'))
    assert formatted_num_bins_df['bools'].equals(pd.Series([1, 0, 1, 0], dtype='int8'))
    assert formatted_num_bins_df['categories'].equals(pd.Series([0, 1, 1, 0], dtype='int8'))
    assert formatted_num_bins_df['dates'].equals(pd.Series([2, 1, 3, 0], dtype='int8'))


def test_datatable_same_mutual_information(df_same_mi):
    dt_same_mi = DataTable(df_same_mi)

    mi = dt_same_mi.mutual_information()

    cols_used = set(np.unique(mi[['column_1', 'column_2']].values))
    assert 'nans' not in cols_used
    assert 'nat_lang' not in cols_used
    assert mi.shape[0] == 1
    assert mi_between_cols('floats', 'ints', mi) == 1.0


def test_datatable_mutual_information(df_mi):
    dt = DataTable(df_mi, logical_types={'dates': Datetime(datetime_format='%Y-%m-%d')})
    original_df = dt.to_dataframe().copy()
    mi = dt.mutual_information()
    assert mi.shape[0] == 10

    np.testing.assert_almost_equal(mi_between_cols('ints', 'bools', mi), 1.0, 3)
    np.testing.assert_almost_equal(mi_between_cols('ints', 'strs', mi), 0.0, 3)
    np.testing.assert_almost_equal(mi_between_cols('strs', 'bools', mi), 0, 3)
    np.testing.assert_almost_equal(mi_between_cols('dates', 'ints', mi), 0.274, 3)
    np.testing.assert_almost_equal(mi_between_cols('dates', 'bools', mi), 0.274, 3)

    mi_many_rows = dt.mutual_information(nrows=100000)
    pd.testing.assert_frame_equal(mi, mi_many_rows)

    mi = dt.mutual_information(nrows=1)
    assert mi.shape[0] == 0

    mi = dt.mutual_information(num_bins=2)
    assert mi.shape[0] == 10
    np.testing.assert_almost_equal(mi_between_cols('bools', 'ints', mi), 0, 3)
    np.testing.assert_almost_equal(mi_between_cols('strs', 'ints', mi), 1.0, 3)
    np.testing.assert_almost_equal(mi_between_cols('bools', 'strs', mi), 0, 3)
    np.testing.assert_almost_equal(mi_between_cols('dates', 'strs', mi), 1.0, 3)
    np.testing.assert_almost_equal(mi_between_cols('dates', 'ints', mi), 1.0, 3)

    # Confirm that none of this changed the DataTable's underlying df
    pd.testing.assert_frame_equal(to_pandas(dt.to_dataframe()), to_pandas(original_df))


def test_mutual_info_does_not_include_index(sample_df):
    dt = DataTable(sample_df, index='id')
    mi = dt.mutual_information()
    assert 'id' not in mi['column_1'].values


def test_mutual_info_returns_empty_df_properly(sample_df):
    dt = DataTable(sample_df.copy()[['id', 'age']], index='id')
    mi = dt.mutual_information()
    assert mi.empty


def test_mutual_info_sort(df_mi):
    dt = DataTable(df_mi)
    mi = dt.mutual_information()

    for i in range(len(mi['mutual_info']) - 1):
        assert mi['mutual_info'].iloc[i] >= mi['mutual_info'].iloc[i + 1]


def test_mutual_info_unique(df_mi_unique):
    dt = DataTable(df_mi_unique)
    mi = dt.mutual_information()

    cols_used = set(np.unique(mi[['column_1', 'column_2']].values))
    assert 'unique' not in cols_used
    assert 'unique_with_one_nan' not in cols_used
    assert 'unique_with_nans' in cols_used
    assert 'ints' in cols_used


def test_mutual_info_dict(df_mi):
    dt = DataTable(df_mi)
    mi_dict = dt.mutual_information_dict()
    mi = dt.mutual_information()

    pd.testing.assert_frame_equal(pd.DataFrame(mi_dict), mi)


def test_datatable_describe_with_no_match(sample_df):
    dt = DataTable(sample_df)
    df = dt.describe(include=['wrongname'])
    assert df.empty


def test_datatable_equality(sample_combos):
    sample_df, sample_series = sample_combos
    dt_basic = DataTable(sample_df)
    dt_basic2 = DataTable(sample_df.copy())
    dt_names = DataTable(sample_df, name='test')

    assert dt_basic != dt_names
    assert dt_basic == dt_basic2
    dt_basic2.pop('id')
    assert dt_basic != dt_basic2

    dt_index = DataTable(sample_df, index='id')
    dt_time_index = DataTable(sample_df, time_index='signup_date')
    dt_set_index = dt_basic.set_index('id')

    assert dt_basic != dt_index
    assert dt_index == dt_set_index
    assert dt_index != dt_time_index

    # Check datatable with same parameters but changed underlying df
    # We only check underlying data for equality with pandas dataframes
    dt_set_index['phone_number'] = DataColumn(sample_series.rename('phone_number'), logical_type='NaturalLanguage')
    if isinstance(dt_index.to_dataframe(), pd.DataFrame):
        assert dt_index != dt_set_index
    else:
        assert dt_index == dt_set_index

    dt_numeric_time_index = DataTable(sample_df, time_index='id')

    assert dt_time_index != dt_numeric_time_index

    dt_with_ltypes = DataTable(sample_df, time_index='id', logical_types={'full_name': 'categorical'})
    assert dt_with_ltypes != dt_time_index
    assert dt_with_ltypes == dt_numeric_time_index.set_types(logical_types={'full_name': Categorical})
    assert dt_with_ltypes != dt_numeric_time_index.set_types(logical_types={'full_name': Categorical()})

    dt_with_metadata = DataTable(sample_df, index='id', table_metadata={'created_by': 'user1'})
    assert DataTable(sample_df, index='id') != dt_with_metadata
    assert DataTable(sample_df, index='id', table_metadata={'created_by': 'user1'}) == dt_with_metadata
    assert DataTable(sample_df, index='id', table_metadata={'created_by': 'user2'}) != dt_with_metadata


def test_datatable_rename_errors(sample_df):
    dt = DataTable(sample_df, index='id', time_index='signup_date')

    error = 'New columns names must be unique from one another.'
    with pytest.raises(ValueError, match=error):
        dt.rename({'age': 'test', 'full_name': 'test'})

    error = 'Column to rename must be present in the DataTable. not_present is not present in the DataTable.'
    with pytest.raises(KeyError, match=error):
        dt.rename({'not_present': 'test'})

    error = 'Cannot rename index or time index columns such as id.'
    with pytest.raises(KeyError, match=error):
        dt.rename({'id': 'test', 'age': 'test2'})

    error = 'The column email is already present in the DataTable. Please choose another name to rename age to or also rename age.'
    with pytest.raises(ValueError, match=error):
        dt.rename({'age': 'email'})


def test_datatable_rename(sample_df):
    table_metadata = {'table_info': 'this is text'}
    id_description = 'the id of the row'
    dt = DataTable(sample_df, index='id',
                   time_index='signup_date',
                   table_metadata=table_metadata,
                   column_descriptions={'id': id_description})
    original_df = to_pandas(dt.to_dataframe()).copy()

    dt_renamed = dt.rename({'age': 'birthday'})
    new_df = to_pandas(dt_renamed.to_dataframe())

    # Confirm underlying data of original datatable hasn't changed
    assert to_pandas(dt.to_dataframe()).equals(original_df)

    assert 'age' not in dt_renamed.columns
    assert 'birthday' in dt_renamed.columns
    assert 'age' not in new_df.columns
    assert 'birthday' in new_df.columns
    assert original_df.columns.get_loc('age') == new_df.columns.get_loc('birthday')
    pd.testing.assert_series_equal(original_df['age'], new_df['birthday'], check_names=False)

    # confirm that metadata and descriptions are there
    assert dt_renamed.metadata == table_metadata
    assert dt['id'].description == id_description

    old_col = dt['age']
    new_col = dt_renamed['birthday']
    pd.testing.assert_series_equal(to_pandas(old_col.to_series()), to_pandas(new_col.to_series()), check_names=False)
    assert old_col.logical_type == new_col.logical_type
    assert old_col.semantic_tags == new_col.semantic_tags
    assert old_col.dtype == new_col.dtype

    dt_swapped_names = dt.rename({'age': 'full_name', 'full_name': 'age'})
    new_df = to_pandas(dt_swapped_names.to_dataframe())

    pd.testing.assert_series_equal(original_df['age'], new_df['full_name'], check_names=False)
    pd.testing.assert_series_equal(original_df['full_name'], new_df['age'], check_names=False)

    assert original_df.columns.get_loc('age') == new_df.columns.get_loc('full_name')
    assert original_df.columns.get_loc('full_name') == new_df.columns.get_loc('age')

    # Swap names back and confirm that order of columns is the same as the original
    dt_swapped_back = dt_swapped_names.rename({'age': 'full_name', 'full_name': 'age'})
    check_column_order(dt, dt_swapped_back)


def test_datatable_sizeof(sample_df):
    dt = DataTable(sample_df)
    if isinstance(sample_df, pd.DataFrame):
        expected_size = 1069
    else:
        expected_size = 32
    assert dt.__sizeof__() == expected_size


def test_datatable_len(sample_df):
    dt = DataTable(sample_df)
    assert len(dt) == len(sample_df) == 4


def test_datatable_update_dataframe(sample_df):
    new_df = sample_df.copy().tail(2).reset_index(drop=True)
    if dd and isinstance(sample_df, dd.DataFrame):
        new_df = dd.from_pandas(new_df, npartitions=1)

    dt = DataTable(sample_df,
                   index='id',
                   time_index='signup_date',
                   logical_types={'full_name': 'FullName'},
                   semantic_tags={'phone_number': 'custom_tag'})
    original_types = dt.types

    dt.update_dataframe(new_df)
    assert len(dt._dataframe) == 2
    assert dt.index == 'id'
    assert dt.time_index == 'signup_date'
    pd.testing.assert_frame_equal(original_types, dt.types)

    if isinstance(new_df, pd.DataFrame):
        new_df = new_df.set_index('id', drop=False)
        new_df.index.name = None
    # new_df does not have updated dtypes, so ignore during check
    pd.testing.assert_frame_equal(to_pandas(new_df),
                                  to_pandas(dt._dataframe),
                                  check_dtype=False,
                                  check_index_type=False)

    # confirm that DataColumn series matches corresponding dataframe column
    for col in dt.columns:
        assert to_pandas(dt.columns[col]._series).equals(to_pandas(dt._dataframe[col]))
        assert dt.columns[col]._series.dtype == dt._dataframe[col].dtype


def test_datatable_update_dataframe_different_num_cols(sample_df):
    new_df = sample_df.copy().drop(columns='age')
    dt = DataTable(sample_df)
    error_msg = 'Updated dataframe contains 6 columns, expecting 7'
    with pytest.raises(ValueError, match=error_msg):
        dt.update_dataframe(new_df)


def test_datatable_update_dataframe_missing_col(sample_df):
    new_df = sample_df.copy().rename(columns={'age': 'old_age'})
    dt = DataTable(sample_df)
    error_msg = 'Updated dataframe is missing new age column'
    with pytest.raises(ValueError, match=error_msg):
        dt.update_dataframe(new_df)


def test_datatable_metadata(sample_df):
    metadata = {'secondary_time_index': {'is_registered': 'age'}, 'date_created': '11/13/20'}

    dt = DataTable(sample_df)
    assert dt.metadata == {}

    dt.metadata = metadata
    assert dt.metadata == metadata

    dt = DataTable(sample_df, time_index='signup_date', table_metadata=metadata)
    assert dt.metadata == metadata

    new_data = {'date_created': '1/1/19', 'created_by': 'user1'}
    dt.metadata = {**metadata, **new_data}
    assert dt.metadata == {'secondary_time_index': {'is_registered': 'age'},
                           'date_created': '1/1/19',
                           'created_by': 'user1'}

    dt.metadata.pop('created_by')
    assert dt.metadata == {'secondary_time_index': {'is_registered': 'age'}, 'date_created': '1/1/19'}

    dt.metadata['number'] = 1012034
    assert dt.metadata == {'number': 1012034,
                           'secondary_time_index': {'is_registered': 'age'},
                           'date_created': '1/1/19'}


def test_datatable_column_order_after_rename(sample_df_pandas):
    # Since rename removes a column to rename it, its location in the dt.columns dictionary
    # changes, so we have to check that we aren't relying on the columns dictionary
    dt = DataTable(sample_df_pandas, index='id', semantic_tags={'full_name': 'test'})
    assert dt.iloc[:, 1].name == 'full_name'
    assert dt.index == 'id'

    renamed_dt = dt.rename({'full_name': 'renamed_col'})
    assert renamed_dt.iloc[:, 1].name == 'renamed_col'

    changed_index_dt = renamed_dt.set_index('renamed_col')
    assert changed_index_dt.index == 'renamed_col'
    check_column_order(renamed_dt, changed_index_dt)

    reset_tags_dt = renamed_dt.reset_semantic_tags(columns='renamed_col')
    assert reset_tags_dt['renamed_col'].semantic_tags == set()
    check_column_order(renamed_dt, reset_tags_dt)


def test_datatable_already_sorted(sample_unsorted_df):
    if dd and isinstance(sample_unsorted_df, dd.DataFrame):
        pytest.xfail('Sorting dataframe is not supported with Dask input')
    if ks and isinstance(sample_unsorted_df, ks.DataFrame):
        pytest.xfail('Sorting dataframe is not supported with Koalas input')

    dt = DataTable(sample_unsorted_df,
                   name='datatable',
                   index='id',
                   time_index='signup_date')

    assert dt.time_index == 'signup_date'
    assert dt.columns[dt.time_index].logical_type == Datetime

    sorted_df = to_pandas(sample_unsorted_df).sort_values(['signup_date', 'id']).set_index('id', drop=False)
    sorted_df.index.name = None
    pd.testing.assert_frame_equal(sorted_df,
                                  to_pandas(dt._dataframe))
    for col in dt.columns:
        assert to_pandas(dt.columns[col]._series).equals(to_pandas(dt._dataframe[col]))

    dt = DataTable(sample_unsorted_df,
                   name='datatable',
                   index='id',
                   time_index='signup_date',
                   already_sorted=True)

    assert dt.time_index == 'signup_date'
    assert dt.columns[dt.time_index].logical_type == Datetime
    unsorted_df = to_pandas(sample_unsorted_df.set_index('id', drop=False))
    unsorted_df.index.name = None
    pd.testing.assert_frame_equal(unsorted_df, to_pandas(dt._dataframe))

    for col in dt.columns:
        assert to_pandas(dt.columns[col]._series).equals(to_pandas(dt._dataframe[col]))


def test_datatable_update_dataframe_already_sorted(sample_unsorted_df):
    if dd and isinstance(sample_unsorted_df, dd.DataFrame):
        pytest.xfail('Sorting dataframe is not supported with Dask input')
    if ks and isinstance(sample_unsorted_df, ks.DataFrame):
        pytest.xfail('Sorting dataframe is not supported with Koalas input')

    index = 'id'
    time_index = 'signup_date'
    sorted_df = sample_unsorted_df.sort_values([time_index, index])
    dt = DataTable(sorted_df,
                   name='datatable',
                   index='id',
                   time_index='signup_date',
                   already_sorted=True)

    dt.update_dataframe(sample_unsorted_df, already_sorted=False)
    sorted_df = sorted_df.set_index('id', drop=False)
    sorted_df.index.name = None
    assert (sorted_df.index == dt._dataframe.index).all()
    for col in dt.columns:
        assert (to_pandas(dt._dataframe[col]) == to_pandas(sorted_df[col])).all()
        assert to_pandas(dt.columns[col]._series).equals(to_pandas(dt._dataframe[col]))

    dt.update_dataframe(sample_unsorted_df, already_sorted=True)
    unsorted_df = to_pandas(sample_unsorted_df.set_index('id', drop=False))
    unsorted_df.index.name = None
    pd.testing.assert_frame_equal(unsorted_df, to_pandas(dt._dataframe), check_dtype=False)
    for col in dt.columns:
        assert to_pandas(dt.columns[col]._series).equals(to_pandas(dt._dataframe[col]))


def test_datatable_init_with_col_descriptions(sample_df):
    descriptions = {
        'age': 'age of the user',
        'signup_date': 'date of account creation'
    }
    dt = DataTable(sample_df, column_descriptions=descriptions)
    for name, column in dt.columns.items():
        assert column.description == descriptions.get(name)


def test_datatable_col_descriptions_warnings(sample_df):
    err_msg = 'column_descriptions must be a dictionary'
    with pytest.raises(TypeError, match=err_msg):
        DataTable(sample_df, column_descriptions=34)

    descriptions = {
        'invalid_col': 'not a valid column',
        'signup_date': 'date of account creation'
    }
    err_msg = re.escape("column_descriptions contains columns that are not present in dataframe: ['invalid_col']")
    with pytest.raises(LookupError, match=err_msg):
        DataTable(sample_df, column_descriptions=descriptions)


def test_datatable_drop(sample_df):
    original_columns = sample_df.columns.copy()
    original_dt = DataTable(sample_df.copy())
    assert set(original_dt.columns.keys()) == set(original_columns)

    single_input_dt = original_dt.drop('is_registered')
    assert len(single_input_dt.columns) == (len(original_columns) - 1)
    assert 'is_registered' not in single_input_dt.columns
    assert to_pandas(original_dt._dataframe).drop('is_registered', axis='columns').equals(to_pandas(single_input_dt._dataframe))

    list_input_dt = original_dt.drop(['is_registered'])
    assert len(list_input_dt.columns) == (len(original_columns) - 1)
    assert 'is_registered' not in list_input_dt.columns
    assert to_pandas(original_dt._dataframe).drop('is_registered', axis='columns').equals(to_pandas(list_input_dt._dataframe))
    # should be equal to the single input example above
    assert single_input_dt == list_input_dt
    assert to_pandas(single_input_dt._dataframe).equals(to_pandas(list_input_dt._dataframe))

    multiple_list_dt = original_dt.drop(['age', 'full_name', 'is_registered'])
    assert len(multiple_list_dt.columns) == (len(original_columns) - 3)
    assert 'is_registered' not in multiple_list_dt.columns
    assert 'full_name' not in multiple_list_dt.columns
    assert 'age' not in multiple_list_dt.columns

    assert to_pandas(original_dt._dataframe).drop(['is_registered', 'age', 'full_name'], axis='columns').equals(to_pandas(multiple_list_dt._dataframe))

    # Drop the same columns in a different order and confirm resulting DataTable column order doesn't change
    different_order_dt = original_dt.drop(['is_registered', 'age', 'full_name'])
    check_column_order(different_order_dt, multiple_list_dt)
    assert different_order_dt == multiple_list_dt
    assert to_pandas(multiple_list_dt._dataframe).equals(to_pandas(different_order_dt._dataframe))


def test_datatable_falsy_column_names(falsy_names_df):
    if dd and isinstance(falsy_names_df, dd.DataFrame):
        pytest.xfail('Dask DataTables cannot handle integer column names')

    dt = DataTable(falsy_names_df.copy(), index=0, time_index='')
    assert dt.index == 0
    assert dt.time_index == ''

    for col_name in falsy_names_df.columns:
        dc = dt[col_name]
        assert dc.name == col_name
        assert dc._series.name == col_name

    dt.time_index = None
    assert dt.time_index is None

    popped_col = dt.pop('')
    dt[''] = popped_col
    assert dt[''].name == ''
    assert dt['']._series.name == ''

    dt = dt.rename({'': 'col_with_name'})
    assert '' not in dt.columns
    assert 'col_with_name' in dt.columns
