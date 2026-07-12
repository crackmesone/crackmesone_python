"""Route-level coverage for search filtering, sorting, and input fallback."""


def _another_crackme(db, sample_crackme):
    item = dict(sample_crackme)
    item.pop('_id')
    item.update({
        'hexid': '507f1f77bcf86cd799439011',
        'name': 'Windows Puzzle',
        'author': 'bob',
        'lang': 'Python',
        'arch': 'ARM',
        'platform': 'Windows',
        'difficulty': 5.0,
        'quality': 3.0,
        'size': 2 * 1024 * 1024,
    })
    db.crackme.insert_one(item)
    return item


def test_search_filters_by_name_and_platform(client, db, sample_crackme):
    _another_crackme(db, sample_crackme)

    response = client.post('/search', data={
        'name': 'Windows',
        'platform': 'Windows',
        'difficulty-min': '1', 'difficulty-max': '6',
        'quality-min': '1', 'quality-max': '6',
    })

    assert response.status_code == 200
    assert b'Windows Puzzle' in response.data
    assert b'Test Crackme' not in response.data


def test_search_applies_size_units_and_sorting(client, db, sample_crackme):
    _another_crackme(db, sample_crackme)

    response = client.post('/search', data={
        'difficulty-min': '1', 'difficulty-max': '6',
        'quality-min': '1', 'quality-max': '6',
        'size-min': '1', 'size-min-unit': 'MB',
        'sort_by': 'size', 'sort_order': 'desc',
    })

    assert response.status_code == 200
    assert b'Windows Puzzle' in response.data
    assert b'Test Crackme' not in response.data


def test_search_invalid_numeric_and_sort_inputs_fall_back_safely(
        client, sample_crackme):
    response = client.post('/search', data={
        'difficulty-min': 'invalid', 'difficulty-max': 'invalid',
        'quality-min': 'invalid', 'quality-max': 'invalid',
        'downloads-min': '-20', 'page': '-4',
        'sort_by': 'drop-table', 'sort_order': 'sideways',
    })

    assert response.status_code == 200
    assert b'Test Crackme' in response.data

def test_random_route_returns_visible_crackmes(client, sample_crackme):
    response = client.get('/random?sort_by=difficulty&sort_order=asc')

    assert response.status_code == 200
    assert b'Test Crackme' in response.data
