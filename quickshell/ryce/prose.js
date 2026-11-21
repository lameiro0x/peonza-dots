.pragma library

// Papel's Spanish prose: the hour said in words («Las diez y cuarto»), numbers in words
// and lowercase roman numerals, as a printed book sets them. Pure functions, no Qt: node
// runs this file against quickshell/tests/prose_es.json, the fixture the lock's Python
// mirror reads too, so the desk and the lock never say the same minute two ways.
// The rule: a 12-hour face. :00 «en punto», :15 «y cuarto», :30 «y media», 1-39 «y» the
// minutes, 40-59 «menos» what is left to the next hour, :45 «menos cuarto». 00:00 and
// 12:00 have names of their own, Medianoche and Mediodía. The hour is feminine (la una),
// the minutes masculine (y uno).

const UNITS = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve",
               "diez", "once", "doce", "trece", "catorce", "quince", "dieciséis", "diecisiete",
               "dieciocho", "diecinueve", "veinte", "veintiuno", "veintidós", "veintitrés",
               "veinticuatro", "veinticinco", "veintiséis", "veintisiete", "veintiocho", "veintinueve"];
const TENS = ["", "", "", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa"];

// 0-99 in words; `feminine` turns a trailing «uno» into «una» (una tarea, veintiuna).
// Anything else comes back in digits.
function number(n, feminine) {
    if (!Number.isInteger(n) || n < 0 || n > 99) return String(n);
    const words = n < 30 ? UNITS[n] : TENS[Math.floor(n / 10)] + (n % 10 === 0 ? "" : " y " + UNITS[n % 10]);
    return feminine ? words.replace(/uno$/, "una") : words;
}

// Lowercase roman numerals, 1-3999 («xlvii»); "" outside that range.
function roman(n) {
    if (!Number.isInteger(n) || n < 1 || n > 3999) return "";
    const marks = [[1000, "m"], [900, "cm"], [500, "d"], [400, "cd"], [100, "c"], [90, "xc"],
                   [50, "l"], [40, "xl"], [10, "x"], [9, "ix"], [5, "v"], [4, "iv"], [1, "i"]];
    let out = "";
    for (const [value, mark] of marks)
        for (; n >= value; n -= value) out += mark;
    return out;
}

// The hour `h` (0-23) and minute `m` (0-59) in words, capitalised.
function hour(h, m) {
    if (m === 0 && h % 12 === 0) return h === 0 ? "Medianoche" : "Mediodía";
    const ahead = m >= 40;
    const twelve = ((ahead ? h + 1 : h) % 12) || 12;
    const head = (twelve === 1 ? "La " : "Las ") + number(twelve, true);
    const tail = m === 0 ? "en punto"
        : m === 15 ? "y cuarto"
        : m === 30 ? "y media"
        : m === 45 ? "menos cuarto"
        : ahead ? "menos " + number(60 - m, false)
        : "y " + number(m, false);
    return head + " " + tail;
}

// The part of the day the hour `h` belongs to, as the phrase's second line; nothing at
// midnight and noon, whose names already say it.
function partOfDay(h, m) {
    if (m === 0 && h % 12 === 0) return "";
    return h >= 1 && h <= 5 ? "de la madrugada"
        : h >= 6 && h <= 11 ? "de la mañana"
        : h === 12 ? "del mediodía"
        : h >= 13 && h <= 20 ? "de la tarde"
        : "de la noche";
}
