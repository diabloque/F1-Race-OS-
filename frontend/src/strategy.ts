// Simple teaching models. Inputs are assumptions, not measurements.
export function temperatureModel(
  start: number,
  air: number,
  heating: number,
  low: number,
  high: number,
  laps: number,
  grainingRate = 0.02,
  overheatingRate = 0.02,
) {
  let temperature = start;
  let damage = 0;
  return Array.from({ length: laps }, (_, index) => {
    temperature += heating - 0.12 * (temperature - air);
    const outside = Math.max(0, low - temperature, temperature - high);
    damage +=
      Math.max(0, low - temperature) * grainingRate +
      Math.max(0, temperature - high) * overheatingRate;
    const grip = Math.max(0, 100 - outside * 0.6 - index * 0.15 - damage);
    return { lap: index + 1, temperature, grip, damage };
  });
}

export function pressureModel(
  pressure: number,
  initialTemp: number,
  finalTemp: number,
  staticLoad: number,
  downforce: number,
  speed: number,
) {
  // Gauge pressure is relative to the atmosphere; the gas law uses absolute pressure.
  const finalPressure =
    ((pressure + 1.01325) * (finalTemp + 273.15)) / (initialTemp + 273.15) - 1.01325;
  const load = staticLoad + downforce * (speed / 300) ** 2;
  return {
    finalPressure,
    load,
    contactArea: finalPressure > 0 ? (load / (finalPressure * 100000)) * 10000 : null,
  };
}

export function pitStrategy(
  laps: number,
  pitLap: number,
  oldPace: number,
  oldAge: number,
  oldDeg: number,
  newPace: number,
  newDeg: number,
  pitLoss: number,
  outLapLoss: number,
  trafficLoss: number,
) {
  let total = 0;
  return Array.from({ length: laps }, (_, i) => {
    const lap = i + 1;
    // The stop happens at the end of the chosen lap; the next lap is the out-lap.
    const time =
      lap <= pitLap
        ? oldPace + oldDeg * (oldAge + i) + (lap === pitLap ? pitLoss : 0)
        : newPace +
          newDeg * (lap - pitLap - 1) +
          (lap === pitLap + 1 ? outLapLoss + trafficLoss : 0);
    total += time;
    return total;
  });
}
