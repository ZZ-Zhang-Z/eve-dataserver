import http.client

conn = http.client.HTTPSConnection("esi.evetech.net")

headers = {
    'Accept-Language': "",
    'X-Compatibility-Date': "2026-06-09",
    'X-Tenant': "",
    'Accept': "application/json"
}

conn.request("GET", "/markets/10000002/types", headers=headers)

res = conn.getresponse()
data = res.read()

print(data.decode("utf-8"))