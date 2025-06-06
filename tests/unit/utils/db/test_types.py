# SPDX-License-Identifier: Apache-2.0

import datetime

import pytz

from sqlalchemy.dialects.postgresql import dialect

from warehouse.utils.db.types import TZDateTime


def test_tzdatetime_bind_nonnaive_datetime():
    dt_field = TZDateTime()
    utc_datetime = pytz.UTC.localize(datetime.datetime.now())
    assert utc_datetime.tzinfo is not None

    naive_datetime = dt_field.process_bind_param(utc_datetime, dialect)
    assert naive_datetime
    assert naive_datetime.tzinfo is None


def test_tzdatetime_bind_nonnaive_datetime_naive():
    dt_field = TZDateTime()
    naive_datetime = datetime.datetime.now()
    assert naive_datetime.tzinfo is None

    assert dt_field.process_bind_param(naive_datetime, dialect) is naive_datetime


def test_tzdatetime_bind_nonnaive_datetime_none():
    dt_field = TZDateTime()

    assert dt_field.process_bind_param(None, dialect) is None


def test_tzdatetime_process_result_value():
    dt_field = TZDateTime()
    naive_datetime = datetime.datetime.now(datetime.UTC)

    utc_datetime = dt_field.process_result_value(naive_datetime, dialect)
    assert utc_datetime
    assert utc_datetime.tzinfo is not None


def test_tzdatetime_process_result_value_none():
    dt_field = TZDateTime()

    assert dt_field.process_result_value(None, dialect) is None
