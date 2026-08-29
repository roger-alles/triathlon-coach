// Ajudes pures per dibuixar polilínies SVG a partir de sèries temporals.

export function polylinePoints(
  values: (number | null)[],
  width: number,
  height: number,
  min: number,
  max: number
): string {
  const n = values.length;
  const span = max - min || 1;
  return values
    .map((v, i) => {
      if (v == null) return null;
      const x = n === 1 ? 0 : (i / (n - 1)) * width;
      const y = height - ((v - min) / span) * height;
      return `${x},${y}`;
    })
    .filter(Boolean)
    .join(' ');
}

export function extent(series: number[][], marginRatio = 0): { min: number; max: number } {
  const all = series.flat();
  const rawMin = Math.min(...all);
  const rawMax = Math.max(...all);
  const margin = (rawMax - rawMin) * marginRatio;
  return { min: rawMin - margin, max: rawMax + margin };
}
