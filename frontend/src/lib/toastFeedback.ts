import { message } from "antd";

/** 统一操作反馈：成功 / 失败 / 警告均走 antd toast。 */
export function toastSuccess(text: string, duration = 3) {
  message.success(text, duration);
}

export function toastError(text: string, duration = 4) {
  message.error(text, duration);
}

export function toastWarning(text: string, duration = 4) {
  message.warning(text, duration);
}

export function toastInfo(text: string, duration = 3) {
  message.info(text, duration);
}

/** 根据文案推断成功或失败并弹出 toast。 */
export function toastOperationResult(text: string) {
  const t = text.trim();
  if (!t) return;
  if (
    t.includes("已保存") ||
    t.includes("已创建") ||
    t.includes("通过") ||
    t.includes("成功") ||
    t === "测试完成"
  ) {
    toastSuccess(t);
  } else {
    toastError(t);
  }
}
