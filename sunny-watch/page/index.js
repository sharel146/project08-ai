/* global Page, getApp, hmUI */

// The GTR 3 Pro is a 480x480 round screen and has no keyboard, so we talk to
// Sunny with tap-to-send quick messages and show her reply. (Voice input could
// be added later if a speech API is available for your firmware.)

const QUICK_MESSAGES = [
  "Good morning",
  "What's on today?",
  "Turn on the desk lamp",
  "Anything I should know?",
];

const W = 480;

Page({
  build() {
    const { messageBuilder } = getApp()._options.globalData;

    hmUI.createWidget(hmUI.widget.TEXT, {
      x: 0,
      y: 40,
      w: W,
      h: 50,
      color: 0xffd166,
      text_size: 40,
      align_h: hmUI.align.CENTER_H,
      text: "Sunny",
    });

    const reply = hmUI.createWidget(hmUI.widget.TEXT, {
      x: 40,
      y: 100,
      w: W - 80,
      h: 150,
      color: 0xffffff,
      text_size: 26,
      align_h: hmUI.align.CENTER_H,
      align_v: hmUI.align.CENTER_V,
      text_style: hmUI.text_style.WRAP,
      text: "Tap a message to talk to Sunny.",
    });

    const ask = (text) => {
      reply.setProperty(hmUI.prop.TEXT, "Asking Sunny…");
      messageBuilder
        .request({ method: "ASK_SUNNY", text })
        .then((res) => {
          const payload = (res && res.data) || {};
          reply.setProperty(
            hmUI.prop.TEXT,
            payload.reply || payload.error || "No reply."
          );
        })
        .catch((err) => {
          reply.setProperty(hmUI.prop.TEXT, "Couldn't reach Sunny:\n" + err);
        });
    };

    // Lay the quick-message buttons out down the lower half of the screen.
    let y = 270;
    for (const text of QUICK_MESSAGES) {
      hmUI.createWidget(hmUI.widget.BUTTON, {
        x: 70,
        y,
        w: W - 140,
        h: 44,
        radius: 22,
        normal_color: 0x1f6feb,
        press_color: 0x388bfd,
        text_size: 24,
        color: 0xffffff,
        text,
        click_func: () => ask(text),
      });
      y += 52;
    }
  },
});
