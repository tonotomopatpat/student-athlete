import { post, request } from "./api";

export type PushState = "unsupported" | "blocked" | "off" | "on";

export const pushSupported = () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

function decodeKey(base64Url: string): Uint8Array<ArrayBuffer> {
  const padded = base64Url.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(base64Url.length / 4) * 4, "=");
  const raw = atob(padded);
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

async function registration() {
  return (await navigator.serviceWorker.getRegistration()) ?? navigator.serviceWorker.register("/sw.js");
}

export async function currentPushState(): Promise<PushState> {
  if (!pushSupported()) return "unsupported";
  if (Notification.permission === "denied") return "blocked";
  const existing = await navigator.serviceWorker.getRegistration();
  const subscription = await existing?.pushManager.getSubscription();
  return subscription ? "on" : "off";
}

export async function enablePush(): Promise<PushState> {
  if (!pushSupported()) return "unsupported";
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return permission === "denied" ? "blocked" : "off";
  const { key } = await request<{ key: string }>("/push/public-key");
  const ready = await registration();
  await navigator.serviceWorker.ready;
  const subscription =
    (await ready.pushManager.getSubscription()) ??
    (await ready.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: decodeKey(key) }));
  const json = subscription.toJSON();
  await post("/push/subscribe", { endpoint: subscription.endpoint, keys: { p256dh: json.keys?.p256dh, auth: json.keys?.auth } });
  return "on";
}

export async function disablePush(): Promise<PushState> {
  const existing = await navigator.serviceWorker.getRegistration();
  const subscription = await existing?.pushManager.getSubscription();
  if (subscription) {
    await post("/push/unsubscribe", { endpoint: subscription.endpoint });
    await subscription.unsubscribe();
  }
  return "off";
}
