import assert from 'node:assert/strict';
import test from 'node:test';
import { loadLocations } from '../locations.mjs';

test('loads locations and displays the JSON response', async () => {
    const locations = [[54.7, -3.27], [53.8, -1.5]];
    const output = { textContent: 'Placeholder' };
    const fetchImpl = async (url) => {
        assert.equal(url, 'http://localhost:8000/locations');
        return {
            ok: true,
            json: async () => locations,
        };
    };

    const result = await loadLocations(
        'http://localhost:8000/locations',
        output,
        fetchImpl
    );

    assert.deepEqual(result, locations);
    assert.equal(output.textContent, JSON.stringify(locations));
});

test('throws for an unsuccessful response without changing the output', async () => {
    const output = { textContent: 'Placeholder' };
    const fetchImpl = async () => ({
        ok: false,
        status: 500,
    });

    await assert.rejects(
        loadLocations('http://localhost:8000/locations', output, fetchImpl),
        /status 500/
    );
    assert.equal(output.textContent, 'Placeholder');
});
