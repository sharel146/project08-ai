/* global AppSideService, fetch */
import { MessageBuilder } from "../shared/message";

// This runs inside the Zepp app ON YOUR PHONE, which is where the network lives.
// The watch sends a request over Bluetooth; we forward it to Sunny's HTTP API
// and send her reply back to the watch.
//
// CONFIGURE THESE:
//   SUNNY_URL   - where Sunny's HTTP API is reachable from your phone. On your
//                 home Wi-Fi this is http://<PC-LAN-IP>:8765/chat. To reach her
//                 from anywhere, put your PC + phone on a Tailscale network and
//                 use the PC's Tailscale IP.
//   SUNNY_TOKEN - must match SUNNY_HTTP_TOKEN in Sunny's .env.
const SUNNY_URL = "http://192.168.1.50:8765/chat";
const SUNNY_TOKEN = "CHANGE-ME-to-match-SUNNY_HTTP_TOKEN";

const messageBuilder = new MessageBuilder();

function askSunny(text) {
  return fetch(SUNNY_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Sunny-Token": SUNNY_TOKEN,
    },
    body: JSON.stringify({ message: text }),
  }).then((response) => {
    // Zepp OS app-side fetch resolves with a `body` string.
    const raw = response && response.body ? response.body : "{}";
    let parsed = {};
    try {
      parsed = JSON.parse(raw);
    } catch (e) {
      parsed = { error: "Bad response from Sunny" };
    }
    return parsed;
  });
}

AppSideService({
  onInit() {
    messageBuilder.listen(() => {});

    messageBuilder.on("request", (ctx) => {
      const req = ctx.request.payload ? ctx.request.payload : ctx.request;
      if (!req || req.method !== "ASK_SUNNY") {
        ctx.response({ data: { error: "unknown request" } });
        return;
      }
      askSunny(req.text)
        .then((data) => ctx.response({ data }))
        .catch((err) => ctx.response({ data: { error: String(err) } }));
    });
  },
  onDestroy() {},
});
