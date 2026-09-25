async def test_auth_is_per_device(api):
    headers = dict(api.headers)
    api.headers.pop("Authorization")
    assert (await api.get("/v1/devices")).status_code == 401
    bad = await api.post("/v1/devices/enroll", json={"name": "x"}, headers={"Authorization": "Bearer wrong"})
    assert bad.status_code == 401

    second = (await api.post("/v1/devices/enroll", json={"name": "iPad"},
                             headers={"Authorization": "Bearer bootstrap-secret"})).json()
    api.headers.update(headers)
    devices = (await api.get("/v1/devices")).json()["devices"]
    assert [d["name"] for d in devices] == ["Dev's iPhone", "iPad"]

    await api.delete(f"/v1/devices/{second['device']['id']}")
    res = await api.get("/v1/devices", headers={"Authorization": f"Bearer {second['token']}"})
    assert res.status_code == 401


async def test_push_token_update(api):
    res = await api.patch("/v1/devices/me", json={"apns_token": "abc123"})
    assert res.json()["push_enabled"] is True


async def test_credentials_go_to_the_vault(api, fake):
    res = await api.post("/v1/integrations/credentials", json={"secret_name": "GITHUB_TOKEN", "value": "ghp_x"})
    assert res.status_code == 201, res.text
    assert "value" not in res.json()
    _, vault_id, kwargs = next(e for e in fake.log if e[0] == "credential.create")
    assert vault_id == "vlt_1"
    assert kwargs["auth"]["type"] == "environment_variable"
    assert kwargs["auth"]["networking"] == {"type": "limited", "allowed_hosts": ["api.github.com", "github.com", "uploads.github.com"]}

    assert (await api.post("/v1/integrations/credentials", json={"secret_name": "GITHUB_TOKEN", "value": "y"})).status_code == 409
    assert (await api.post("/v1/integrations/credentials", json={"secret_name": "MY_KEY", "value": "y"})).status_code == 422
    bad_host = {"secret_name": "MY_KEY", "value": "y", "allowed_hosts": ["https://x.com/path"]}
    assert (await api.post("/v1/integrations/credentials", json=bad_host)).status_code == 422

    schema = (await api.get("/v1/integrations/schema")).json()
    assert {k["secret_name"]: k["configured"] for k in schema["known"]}["GITHUB_TOKEN"] is True

    assert (await api.delete("/v1/integrations/credentials/GITHUB_TOKEN")).status_code == 200
    assert ("credential.archive", "vcrd_1", "vlt_1") in fake.log


async def test_health(api):
    body = (await api.get("/health")).json()
    assert body["agent_configured"] and body["vault_configured"] and body["devices"] == 1
