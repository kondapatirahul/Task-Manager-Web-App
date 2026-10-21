
async function api(method, path, body = null) {
    const options = {
        method,
        headers: {
            "Content-Type": "application/json"
        },
        credentials: "same-origin"
    };

    if (body !== null && body !== undefined) {
        options.body = JSON.stringify(body);
    }

    const response = await fetch(`/api${path}`, options);

    let data = null;

    const contentType = response.headers.get("content-type") || "";

    if (contentType.includes("application/json")) {
        data = await response.json();
    }

    if (!response.ok || data?.ok === false) {
        throw new Error(
            data?.error || data?.message || "Request failed"
        );
    }

    return data;
}
