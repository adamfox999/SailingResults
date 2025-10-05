export const formatDisplayDate = (value: string): string => {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) {
    return value;
  }
  return parsed.toLocaleDateString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
};

export const toDateInputValue = (value: string): string => {
  if (!value) return "";
  return value.length >= 10 ? value.slice(0, 10) : value;
};

export const toTimeInputValue = (value?: string | null): string => {
  if (!value) return "";
  const parts = value.split("T");
  const candidate = parts.length > 1 ? parts[1] : parts[0];
  return candidate.slice(0, 5);
};
