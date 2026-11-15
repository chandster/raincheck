export async function loadLocations(url, outputElement, fetchImpl = globalThis.fetch) {
    const response = await fetchImpl(url);
    if (!response.ok) {
        throw new Error(`Locations request failed with status ${response.status}`);
    }

    const locations = await response.json();
    console.log(locations)
    outputElement.textContent = JSON.stringify(locations);
    return locations;
}
