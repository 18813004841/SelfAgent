export function formatReviewLogData(key, value) {
  if (key === "总耗时" && typeof value === "number" && Number.isFinite(value)) {
    const seconds = Math.max(0, Math.round(value));
    return (
      Math.floor(seconds / 3600) +
      "时" +
      String(Math.floor((seconds % 3600) / 60)).padStart(2, "0") +
      "分" +
      String(seconds % 60).padStart(2, "0") +
      "秒"
    );
  }
  return value;
}
