// Same rollover policy as lexi/schedule.py; no network is needed offline.
import {dateInTimezone} from './selection.js';

export const validUpdateTime = value => typeof value === 'string' && /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value);
const formatters = new Map();

export function deviceTimezone(fallback = 'UTC') {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || fallback;
}

function partsAt(instant, timezone) {
  if (!formatters.has(timezone)) formatters.set(timezone,new Intl.DateTimeFormat('en-GB', {
    timeZone: timezone, hourCycle: 'h23', year: 'numeric', month: '2-digit',
    day: '2-digit', hour: '2-digit', minute: '2-digit',
  }));
  const parts = formatters.get(timezone).formatToParts(new Date(instant));
  const get = name => parts.find(part => part.type === name).value;
  return {day: `${get('year')}-${get('month')}-${get('day')}`, hour: +get('hour'), minute: +get('minute')};
}

function offsetAt(instant, timezone) {
  const part = partsAt(instant, timezone);
  return Date.parse(`${part.day}T${String(part.hour).padStart(2,'0')}:${String(part.minute).padStart(2,'0')}:00Z`) - instant;
}

export function shiftDate(day, amount) {
  return new Date(Date.parse(`${day}T00:00:00Z`) + amount * 86400000).toISOString().slice(0,10);
}

export function rolloverAt(day, updateTime, timezone) {
  if (!validUpdateTime(updateTime)) throw new Error('Choose an update time in HH:MM format.');
  const wall = Date.parse(`${day}T${updateTime}:00Z`);
  const requested = Number(updateTime.slice(0,2)) * 60 + Number(updateTime.slice(3));
  const offsets = new Set([-36,0,36].map(hours => offsetAt(wall + hours * 3600000, timezone)));
  const candidates = [...offsets].map(offset => wall - offset);
  const exact = candidates.filter(instant => {
    const part = partsAt(instant, timezone);
    return part.day === day && part.hour * 60 + part.minute === requested;
  });
  if (exact.length) return Math.min(...exact);
  const forward = candidates.filter(instant => {
    const part = partsAt(instant, timezone);
    return part.day >= day && (part.day > day || part.hour * 60 + part.minute > requested);
  });
  if (!forward.length) throw new Error('The update time could not be resolved.');
  let result = Math.min(...forward);
  for (let index = 0; index < 1440; index++) {
    const part = partsAt(result - 60000, timezone);
    if (part.day !== day || part.hour * 60 + part.minute < requested) return result;
    result -= 60000;
  }
  throw new Error('The update time could not be resolved.');
}

export function dailySchedule(timezone, updateTime, now = new Date()) {
  const calendarDate = dateInTimezone(timezone, now);
  const date = now.getTime() >= rolloverAt(calendarDate, updateTime, timezone) ? calendarDate : shiftDate(calendarDate,-1);
  return {date, calendarDate, timezone, updateTime, nextUpdateAt: new Date(rolloverAt(shiftDate(date,1),updateTime,timezone)).toISOString()};
}
