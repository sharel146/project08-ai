/* global App, getApp */
import { MessageBuilder } from "./shared/message";

// MessageBuilder is the device<->phone bridge. `shared/message.js` is provided
// by the official Zepp OS app template — generate it with `zeus create` (pick a
// communication/fetch sample) and keep it next to this file. See README.
const messageBuilder = new MessageBuilder();

App({
  globalData: {
    messageBuilder,
  },
  onCreate() {
    messageBuilder.connect();
  },
  onDestroy() {
    messageBuilder.disConnect();
  },
});
