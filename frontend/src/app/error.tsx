"use client";

import { useEffect } from "react";
import { Button, Result } from "antd";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // 记录到控制台供生产排查；不主动上报，保留给用户/运维决策。
    console.error("[app-error-boundary]", error);
  }, [error]);

  return (
    <div style={{ padding: 48 }}>
      <Result
        status="error"
        title="出现了意料之外的错误"
        subTitle={error?.message || "请稍后再试，或返回上一页继续。"}
        extra={[
          <Button type="primary" key="retry" onClick={() => reset()}>
            重试
          </Button>,
          <Button key="home" onClick={() => (window.location.href = "/")}>
            返回首页
          </Button>,
        ]}
      />
    </div>
  );
}
