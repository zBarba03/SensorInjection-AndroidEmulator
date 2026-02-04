// inject_sensors.js
// Replay CSV su emulatore Android via Appium (UiAutomator2) usando la console sensori.
// Uso:
//   File locale:  node inject_sensors.js <app> <file.csv>
//   Firebase:     node inject_sensors.js <app> firebase
// <app> ∈ { run, tayutau, accupedo, walklogger, forlani, forlani_register, forlani_results }

require("dotenv").config();
const wdio = require("webdriverio");
const fs = require("fs");
const { parse } = require("csv-parse");
const readline = require("readline");
const path = require("path");
const admin = require("firebase-admin");
//const { spawn } = require("child_process");
import { spawn } from 'node:child_process';

const serviceAccount = require("./serviceAccountKey.json");
admin.initializeApp({
	credential: admin.credential.cert(serviceAccount),
	storageBucket: "pedometercorrection.firebasestorage.app"
});
const bucket = admin.storage().bucket();

const IMMEDIATE_START  = envBool("IMMEDIATE_START", true);

const AXIS_MAP  = (process.env.AXIS_MAP  || "XYZ").toUpperCase();
const AXIS_SIGN = (process.env.AXIS_SIGN || "+++");

const CSV_UNITS       = (process.env.CSV_UNITS || "ms2").toLowerCase();
const CSV_GYRO_UNITS  = (process.env.CSV_GYRO_UNITS || "rad_s").toLowerCase();
const CSV_MAG_UNITS   = (process.env.CSV_MAG_UNITS  || "uT").toLowerCase();
const CSV_HAS_HEADER  = envBool("CSV_HAS_HEADER", true);
const TIMES_ARE_MS    = envBool("CSV_TIMES_ARE_MS", true);
const CSV_LAYOUT      = (process.env.CSV_LAYOUT || "").trim().toLowerCase();
const INJECT_GYRO     = envBool("INJECT_GYRO", true);
const INJECT_MAG      = envBool("INJECT_MAG", true);

const PRE_ROLL_MS     = Number(process.env.PRE_ROLL_MS || 0);
const LOOP_REPEATS    = Number(process.env.LOOP_REPEATS || 1);
const LOOP_GAP_MS     = Number(process.env.LOOP_GAP_MS || 0);

const DROP_NON_MONOTONIC = envBool("DROP_NON_MONOTONIC", true);
const LOG_EVERY_N     = Number(process.env.LOG_EVERY_N || 100);

const G = 9.80665;

const runtasticPath     = process.env.APP_RUN_APK        || "C:/Users/Utente/Downloads/Runtastic Pedometer PRO_1.6.2_apkcombo.com.apk";
const tayutauPath       = process.env.APP_TAYUTAU_APK    || "C:/Users/Utente/Downloads/pedometer-5-47.apk";
const accupedoPath      = process.env.APP_ACCUPEDO_APK   || "C:/Users/Utente/Downloads/accupedo-pedometer-9-1-5-1.apk";
const walkloggerPath    = process.env.APP_WALKLOGGER_APK || "C:/Users/Utente/Downloads/walklogger-pedometer.apk";
const forlaniPath       = process.env.APP_FORLANI_APK    || "./steplab.apk";
const motiontrackerPath = process.env.APP_MOTIONTRACKER_APK || "./motiontracker.apk";
const sensorcsvPath     = process.env.APP_SENSORCSV_APK || "./SensorCSV_Jan28.apk";

function envBool(name, def) { const v = process.env[name]; if (v == null) return def; return /^(1|true|yes|y|on)$/i.test(v); }
function isAbsolute(p)      { return /^([A-Za-z]:\\|\/)/.test(p); }
function nowMsMono()        { return Number(process.hrtime.bigint() / 1_000_000n); }
function sleep(ms)          { return new Promise(r => setTimeout(r, ms)); }

async function listDateFolders() {
	try {
		const [files] = await bucket.getFiles({ prefix: 'motion_data/' });
		const folders = new Set();
		files.forEach(file => {
			const parts = file.name.split('/');
			if (parts.length >= 2 && parts[0] === 'motion_data' && parts[1] && /^\d{4}-\d{2}-\d{2}$/.test(parts[1])) {
				folders.add(parts[1]);
			}
		});
		return Array.from(folders).sort();
	} catch (e) {
		console.error('Errore nel listare le cartelle date:', e);
		return [];
	}
}
async function listCSVFilesInDate(dateFolder) {
	try {
		const [files] = await bucket.getFiles({ prefix: `motion_data/${dateFolder}/` });
		return files
			.filter(f => f.name.endsWith('.csv'))
			.map(f => ({ name: path.basename(f.name), fullPath: f.name, file: f }));
	} catch (e) {
		console.error(`Errore nel listare CSV per ${dateFolder}:`, e);
		return [];
	}
}
async function downloadCSVFile(firebaseFile, localPath) {
	try {
		const destination = path.join(__dirname, 'temp_csv', localPath);
		fs.mkdirSync(path.dirname(destination), { recursive: true });
		await firebaseFile.download({ destination });
		console.log(`Download completato: ${localPath}`);
		return destination;
	} catch (e) {
		console.error(`Errore nel download di ${localPath}:`, e);
		return null;
	}
}
async function selectDateAndDownloadCSVs(appName) {
	if (appName === 'forlani') {
		const config = await askForlaniConfiguration();
		SimulateForlani.currentConfig = config;
		console.log(`\n✓ Configurazione selezionata: ${config}`);
		if (config === 3) {
			const verificationMode = await askVerificationMode();
			SimulateForlani.verificationMode = verificationMode;
			console.log(`✓ Modalità verifica: ${verificationMode ? 'ATTIVA' : 'NON ATTIVA'}`);
		}
	}

	const folders = await listDateFolders();
	if (folders.length === 0) {
		console.log("Nessuna cartella data trovata in Firebase Storage.");
		return [];
	}

	console.log("\n=== SELEZIONE DATA ===");
	folders.forEach((f, i) => console.log(`${i+1}. ${f}`));
	const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
	return new Promise((resolve) => {
		rl.question("Seleziona il numero della data (o 'all' per tutte): ", async (answer) => {
			rl.close();
			let selectedFolders = [];
			if ((answer || '').toLowerCase() === 'all') selectedFolders = folders;
			else {
				const idx = parseInt(answer) - 1;
				if (idx >= 0 && idx < folders.length) selectedFolders = [folders[idx]];
				else { console.log("Selezione non valida."); resolve([]); return; }
			}

			let allFiles = [], skipped = [];
			for (const df of selectedFolders) {
				console.log(`\nScaricando CSV da ${df}...`);
				const csvs = await listCSVFilesInDate(df);
				for (const csv of csvs) {
					if (isFileAlreadyProcessed(appName, csv.name)) { skipped.push(csv.name); continue; }
					const p = await downloadCSVFile(csv.file, path.join(df, csv.name));
					if (p) allFiles.push({ name: csv.name, path: p, dateFolder: df });
				}
			}

			console.log(`\n=== RIEPILOGO DOWNLOAD ===`);
			console.log(`File da processare: ${allFiles.length}`);
			console.log(`File già processati (saltati): ${skipped.length}`);
			if (skipped.length) console.log("File saltati:", skipped.slice(0, 5).join(", ") + (skipped.length > 5 ? "..." : ""));
			resolve(allFiles);
		});
	});
}

function parseFileNameInfo(fileName) {
	const base = path.basename(fileName, path.extname(fileName));
	const parts = base.split('_');
	if (parts.length < 7) return { walkingType:'unknown', phonePosition:'unknown', age:'unknown', gender:'unknown', device:'unknown' };

	const walkingTypes = ['PLAIN_WALKING','RUNNING','IRREGULAR_STEPS','BABY_STEPS','UPHILL_WALKING','DOWNHILL_WALKING'];
	let walkingTypeIdx = -1;
	for (let i = 2; i < parts.length - 4 && walkingTypeIdx === -1; i++) {
		const cand = parts.slice(i).join('_');
		for (const t of walkingTypes) if (cand.startsWith(t)) { walkingTypeIdx = i; break; }
	}
	if (walkingTypeIdx === -1) walkingTypeIdx = 2;

	const positions = ['HAND','SHOULDER','POCKET'];
	let positionIdx = -1;
	for (let i = walkingTypeIdx; i < parts.length - 2; i++) if (positions.includes(parts[i])) { positionIdx = i; break; }

	let walkingType='unknown', phonePosition='unknown', age='unknown', gender='unknown', device='unknown';
	if (positionIdx !== -1) {
		walkingType   = parts.slice(walkingTypeIdx, positionIdx).join('_').toLowerCase().replace(/_/g,' ');
		phonePosition = parts[positionIdx].toLowerCase();
		if (positionIdx+1 < parts.length && /^\d+$/.test(parts[positionIdx+1])) age = parts[positionIdx+1];
		if (positionIdx+2 < parts.length && ['MALE','FEMALE','M','F'].includes(parts[positionIdx+2].toUpperCase())) gender = parts[positionIdx+2].toLowerCase();
		if (positionIdx+3 < parts.length) device = parts.slice(positionIdx+3).join(' ').toLowerCase();
	}
	return { walkingType, phonePosition, age, gender, device };
}
function getAppResultsFile(appName) {
	let filename;
	if (appName === 'forlani') {
		if (!SimulateForlani.currentConfig) throw new Error('Configurazione Forlani non impostata.');
		filename = {
			1:'results_forlani_peak_butterworth.csv',
			2:'results_forlani_peak_intersection_low_pass_10hz.csv',
			3:'results_forlani_peak_low_pass.csv',
			4:'results_forlani_peak_intersection_low_pass_2percent.csv',
			5:'results_forlani_peak_time_filtering_low_pass_10hz.csv',
			6:'results_forlani_time_filtering_peak_butterworth.csv'
		}[SimulateForlani.currentConfig];
	} else {
		filename = `results_${appName}.csv`;
	}
	const filepath = path.join(__dirname, filename);
	if (!fs.existsSync(filepath)) {
		fs.writeFileSync(filepath, "timestamp,csv_file,walking_type,phone_position,age,gender,device,steps_counted\n", "utf8");
		console.log(`Creato nuovo file risultati: ${filename}`);
	} else {
		const first = (fs.readFileSync(filepath, "utf8").split("\n")[0]||"");
		if (!first.includes("walking_type")) {
			fs.writeFileSync(filepath, "timestamp,csv_file,walking_type,phone_position,age,gender,device,steps_counted\n", "utf8");
			console.log(`Aggiornata struttura file: ${filename}`);
		}
	}
	return filepath;
}
function saveStepsResult(appName, csvFile, _csvPath, stepsCount) {
	const resultsFile = getAppResultsFile(appName);
	const timestamp = new Date().toISOString();
	const info = parseFileNameInfo(csvFile);
	const row = `${timestamp},"${csvFile}","${info.walkingType}","${info.phonePosition}","${info.age}","${info.gender}","${info.device}",${stepsCount}\n`;
	fs.appendFileSync(resultsFile, row, "utf8");
	console.log(`Salvato in ${path.basename(resultsFile)}: ${csvFile} -> passi=${stepsCount}`);
}
function saveVerificationResult(csvFile, stepsLive, stepsBatch) {
	const verificationFile = path.join(__dirname, 'verification.csv');
	if (!fs.existsSync(verificationFile)) {
		fs.writeFileSync(verificationFile, "file_name,steps_live,steps_batch,error,absolute_error\n", "utf8");
		console.log("Creato file verification.csv");
	}
	const err = stepsLive - stepsBatch;
	fs.appendFileSync(verificationFile, `"${csvFile}",${stepsLive},${stepsBatch},${err>=0?'+':''}${err},${Math.abs(err)}\n`, "utf8");
}

const LAYOUT_FIELDS = ["t","timestamp","ax","ay","az","gx","gy","gz","mx","my","mz"];
function getLayoutFromEnv() {
	if (!CSV_LAYOUT) return null;
	const parts = CSV_LAYOUT.split(",").map(s => s.trim());
	const m = {};
	parts.forEach((name, idx) => {
		const key = name.toLowerCase();
		if (!LAYOUT_FIELDS.includes(key)) throw new Error(`CSV_LAYOUT contiene campo non valido "${name}"`);
		m[key] = idx;
	});
	return m;
}
function getLayoutFromHeader(headerRow) {
	if (!headerRow) return null;
	const map = {};
	headerRow.forEach((h, i) => {
		const key = String(h).trim().toLowerCase();
		if (LAYOUT_FIELDS.includes(key)) map[key] = i;
	});
	if ((map.t != null || map.timestamp != null) && map.ax != null && map.ay != null && map.az != null) return map;
	return null;
}
function detectCSVLayout(row) {
	const lastIdx = row.length - 1;
	const first = Number(row[0]);
	const last  = Number(row[lastIdx]);
	const looksTime = (v) => Number.isFinite(v) && (v > 1e9 || (!TIMES_ARE_MS && v > 1e6) || (TIMES_ARE_MS && v > 1e3));
	let tIdx = null;
	if (looksTime(last)) tIdx = lastIdx;
	else if (looksTime(first)) tIdx = 0;
	else {
		let bestI = 0, bestV = -Infinity;
		for (let i = 0; i < row.length; i++) { const v = Number(row[i]); if (Number.isFinite(v) && v > bestV) { bestV = v; bestI = i; } }
		tIdx = bestI;
	}
	const idx = { t: tIdx, ax:null, ay:null, az:null, gx:null, gy:null, gz:null, mx:null, my:null, mz:null };
	const numericIdx = [];
	for (let i = 0; i < row.length; i++) if (i !== tIdx && Number.isFinite(Number(row[i]))) numericIdx.push(i);
	const order = ["ax","ay","az","gx","gy","gz","mx","my","mz"];
	for (let j = 0; j < order.length && j < numericIdx.length; j++) idx[order[j]] = numericIdx[j];
	return idx;
}
function pickTimestamp(row, idxMap) {
	const tIdx = (idxMap.timestamp != null) ? idxMap.timestamp : idxMap.t;
	const raw = Number(row[tIdx]);
	if (!Number.isFinite(raw)) return NaN;
	return TIMES_ARE_MS ? raw : (raw / 1e6);
}
function numOrZero (v){ const n = Number(v); return Number.isFinite(n) ? n : 0; }
function pickVec(row, idxMap, kx, ky, kz) {
	const x = numOrZero(row[idxMap[kx] ?? -1]);
	const y = numOrZero(row[idxMap[ky] ?? -1]);
	const z = numOrZero(row[idxMap[kz] ?? -1]);
	return [x, y, z];
}
function mapAxes([x,y,z]) {
	const pick = (c) => (c === "X" ? x : c === "Y" ? y : z);
	const sx = AXIS_SIGN[0] === "-" ? -1 : 1;
	const sy = AXIS_SIGN[1] === "-" ? -1 : 1;
	const sz = AXIS_SIGN[2] === "-" ? -1 : 1;
	return [sx * pick(AXIS_MAP[0]), sy * pick(AXIS_MAP[1]), sz * pick(AXIS_MAP[2])];
}
function scaleAccel([x,y,z]) { const s = (CSV_UNITS === "g") ? G : 1; return [x*s, y*s, z*s]; }
function scaleGyro ([x,y,z]) { const s = (CSV_GYRO_UNITS === "dps") ? (Math.PI/180) : 1; return [x*s, y*s, z*s]; }
function scaleMag  ([x,y,z]) { let s = 1; if (CSV_MAG_UNITS === "t") s=1e6; else if (CSV_MAG_UNITS === "mgauss") s=0.1; return [x*s, y*s, z*s]; }

async function ensureEmulator(driver) {
	try {
		await driver.executeScript('mobile: execEmuConsoleCommand', [{ command: 'help' }]);
	} catch (e) {
		throw new Error(
			'Target non è un emulatore OPPURE manca --allow-insecure "*:emulator_console" su Appium. ' +
			'Avvia Appium con: appium --allow-insecure "*:emulator_console". Dettagli: ' + (e?.message || e)
		);
	}
}

async function emuCmd(driver, command) {
	return driver.executeScript('mobile: execEmuConsoleCommand', [{ command }]);
}

async function injectExactFromCsv(driver, csvPath) {
	const parser = parse({ delimiter:",", from_line:1, relax_column_count:false, skip_empty_lines:true });
	const stream = fs.createReadStream(csvPath).pipe(parser);

	let idxMap = getLayoutFromEnv();
	let rowIdx = 0;
	let firstT = null, wall0Ms = 0;
	const START_AHEAD_MS   = Number(process.env.START_AHEAD_MS || 0);
	const LOCAL_PRE_ROLLMS = Number(process.env.PRE_ROLL_MS || 0);

	for await (const row of stream) {
		rowIdx++;
		if (!row || row.length < 4) continue;

		if (rowIdx === 1 && CSV_HAS_HEADER && !idxMap) {
			const fromHeader = getLayoutFromHeader(row);
			if (fromHeader) { idxMap = fromHeader; continue; }
		}
		if (!idxMap) idxMap = detectCSVLayout(row);

		console.log(`Layout CSV usato: ${JSON.stringify(idxMap)}`);

		const tMs = pickTimestamp(row, idxMap);
		if (!Number.isFinite(tMs)) continue;

		const acc = mapAxes(scaleAccel(pickVec(row, idxMap, "ax","ay","az")));
		const gyr = mapAxes(scaleGyro (pickVec(row, idxMap, "gx","gy","gz")));
		const mag = mapAxes(scaleMag  (pickVec(row, idxMap, "mx","my","mz")));

		const hasAcc = Number.isFinite(acc[0]) && Number.isFinite(acc[1]) && Number.isFinite(acc[2]);
		const hasGyr = INJECT_GYRO && Number.isFinite(gyr[0]) && Number.isFinite(gyr[1]) && Number.isFinite(gyr[2]);
		const hasMag = INJECT_MAG  && Number.isFinite(mag[0]) && Number.isFinite(mag[1]) && Number.isFinite(mag[2]);

		if (firstT == null) {
			firstT = tMs;
			if (!IMMEDIATE_START && LOCAL_PRE_ROLLMS > 0) await sleep(LOCAL_PRE_ROLLMS);
			wall0Ms = nowMsMono() - START_AHEAD_MS;
		}

		const due  = wall0Ms + (tMs - firstT);
		const wait = due - nowMsMono();
		if (wait > 0) await sleep(wait);

		if (hasMag) await emuCmd(driver, `sensor set magnetic-field ${mag[0]}:${mag[1]}:${mag[2]}`);
		if (hasAcc) await emuCmd(driver, `sensor set acceleration ${acc[0]}:${acc[1]}:${acc[2]}`);
		if (hasGyr) await emuCmd(driver, `sensor set gyroscope ${gyr[0]}:${gyr[1]}:${gyr[2]}`);
	}
}

async function SimulateRUN(driver, isFirstTime = true) {
	await sleep(600);
	if (isFirstTime) {
		try { await driver.$(`android=new UiSelector().text("REMIND ME LATER").className("android.widget.Button")`).click(); } catch {}
		await sleep(300);
		try { await driver.$(`android=new UiSelector().text("SKIP")`).click(); } catch {}
		await sleep(300);
	}
	try { await driver.$(`android=new UiSelector().textContains("START WORKOUT")`).click(); } catch {}
}
async function SimulateTayutau(driver, isFirstTime = true) {
	try { await driver.$(`android=new UiSelector().textMatches("(?i)start")`).click(); } catch {}
}
async function SimulateINJECT_GYROAccupedo(driver, isFirstTime = true) {
	//NO OP
}
async function SimulateWalklogger(driver, isFirstTime = true) {
	// NO OP
}
async function SimulateForlani(driver, isFirstTime = true, config = null) {
	if (!config) config = SimulateForlani.currentConfig || 1;
	if (isFirstTime) { try { await driver.$(`android=new UiSelector().text("ENTER CONFIGURATION")`).click(); } catch {} }
	else { try { await driver.$(`android=new UiSelector().text("NEW CONFIGURATION")`).click(); await sleep(500); } catch {} }

	try { const sel=`android=new UiScrollable(new UiSelector().scrollable(true)).scrollTextIntoView("50 Hz")`; await driver.$(sel); } catch {}
	try { await driver.$(`android=new UiSelector().textContains("50 Hz")`).click(); } catch {}

	switch (config) {
		case 1:
			try { const sel=`android=new UiScrollable(new UiSelector().scrollable(true)).scrollTextIntoView("Butterworth Filter")`; await driver.$(sel);} catch {}
			try { await driver.$(`android=new UiSelector().textContains("Butterworth Filter")`).click(); } catch {}
			try { const sel=`android=new UiScrollable(new UiSelector().scrollable(true)).scrollTextIntoView("Peak Algorithm")`; await driver.$(sel);} catch {}
			try { await driver.$(`android=new UiSelector().textContains("Peak Algorithm")`).click(); } catch {}
			break;
		case 2:
			try { const sel=`android=new UiScrollable(new UiSelector().scrollable(true)).scrollTextIntoView("Low-Pass Filter")`; await driver.$(sel);} catch {}
			try { await driver.$(`android=new UiSelector().textContains("Low-Pass Filter")`).click(); } catch {}
			try { const sel=`android=new UiScrollable(new UiSelector().scrollable(true)).scrollTextIntoView("10 Hz")`; await driver.$(sel);} catch {}
			try { await sleep(500); await driver.$(`android=new UiSelector().text("10 Hz")`).click(); } catch {}
			break;
		case 3:
			try { const sel=`android=new UiScrollable(new UiSelector().scrollable(true)).scrollTextIntoView("Peak Algorithm")`; await driver.$(sel);} catch {}
			try { await driver.$(`android=new UiSelector().textContains("Peak Algorithm")`).click(); } catch {}
			try { const sel=`android=new UiScrollable(new UiSelector().scrollable(true)).scrollTextIntoView("Low-Pass Filter")`; await driver.$(sel);} catch {}
			try { await driver.$(`android=new UiSelector().textContains("Low-Pass Filter")`).click(); } catch {}
			break;
		case 4:
			try { const sel=`android=new UiScrollable(new UiSelector().scrollable(true)).scrollTextIntoView("Low-Pass Filter")`; await driver.$(sel);} catch {}
			try { await driver.$(`android=new UiSelector().textContains("Low-Pass Filter")`).click(); } catch {}
			break;
		case 5:
			try { const sel=`android=new UiScrollable(new UiSelector().scrollable(true)).scrollTextIntoView("Time filtering + Peak")`; await driver.$(sel);} catch {}
			try { await driver.$(`android=new UiSelector().textContains("Time filtering + Peak")`).click(); } catch {}
			try { const sel=`android=new UiScrollable(new UiSelector().scrollable(true)).scrollTextIntoView("10 Hz")`; await driver.$(sel);} catch {}
			try { await sleep(500); await driver.$(`android=new UiSelector().text("10 Hz")`).click(); } catch {}
			break;
		case 6:
			try { const sel=`android=new UiScrollable(new UiSelector().scrollable(true)).scrollTextIntoView("Time filtering + Peak")`; await driver.$(sel);} catch {}
			try { await driver.$(`android=new UiSelector().textContains("Time filtering + Peak")`).click(); } catch {}
			try { const sel=`android=new UiScrollable(new UiSelector().scrollable(true)).scrollTextIntoView("Butterworth Filter")`; await driver.$(sel);} catch {}
			try { await sleep(500); await driver.$(`android=new UiSelector().textContains("Butterworth Filter")`).click(); } catch {}
			break;
		default:
			console.warn("Configurazione non valida, uso default (1)");
			config = 1; SimulateForlani.currentConfig = 1;
	}

	await sleep(500);
	try { await driver.$(`android=new UiSelector().textContains("START PEDOMETER")`).click(); } catch {}
}
async function SimulateMotiontracker(driver, isFirstTime = true) {
	// TODO
}
async function SimulateReina(driver, magnitude, injectionFrequency, sensorDelay) {
	const WAIT_AFTER_CLICK = 1200;
	
	//TODO if app is already recording, click "Cancel"
	
	// select parameters in emulator
	try { await driver.$(`android=new UiSelector().textContains("${magnitude}")`).click(); } catch {}
	await sleep(WAIT_AFTER_CLICK);
	try { await driver.$(`android=new UiSelector().textContains("${injectionFrequency}Hz")`).click(); } catch {}
	await sleep(WAIT_AFTER_CLICK);
	try { await driver.$(`android=new UiSelector().textContains("${sensorDelay}")`).click(); } catch {}
	await sleep(WAIT_AFTER_CLICK);
	
	// start recording
	try { await driver.$(`android=new UiSelector().textContains("Start Recording")`).click(); } catch {}
	
	// start python injection script
	const result = await Promise((resolve, reject) => {
    const py = spawn("./mock.py", [magnitude, injectionFrequency, sensorDelay]);
    let stdout = "";
    let stderr = "";
    py.stdout.on("data", (data) => { stdout += data.toString();});
    py.stderr.on("data", (data) => { stderr += data.toString();});
    py.on("close", (code) => {
      if (code !== 0) { reject(new Error(`Python exited with code ${code}\n${stderr}`)); }
      else { resolve(stdout); }
    });
    py.on("error", reject);
  });
	if(result != "") Console.log(result)
	// python script finished with saved log file
	
	// save recording
	try { await driver.$(`android=new UiSelector().textContains("Stop and Save")`).click(); } catch {}
}

function selectApp(arg) {
	switch (arg) {
		case "run":              return runtasticPath;
		case "tayutau":          return tayutauPath;
		case "accupedo":         return accupedoPath;
		case "walklogger":       return walkloggerPath;
		case "forlani":          return forlaniPath;
		case "forlani_register": return forlaniPath;
		case "forlani_results":  return forlaniPath;
		case "motiontracker":    return motiontrackerPath;
		case "reina":            return sensorcsvPath;
		default:
			console.error("App non riconosciuta:", arg);
			process.exit(2);
	}
}
function selectSimulation(arg) {
	switch (arg) {
		case "run":              return SimulateRUN;
		case "tayutau":          return SimulateTayutau;
		case "accupedo":         return SimulateAccupedo;
		case "walklogger":       return SimulateWalklogger;
		case "forlani":          return SimulateForlani;
		case "forlani_register": return SimulateForlaniRegister;
		case "forlani_results":  return SimulateForlaniResults;
		case "motiontracker":    return SimulateMotiontracker;
		case "reina":            return SimulateReina;
		default:                 return async () => {};
	}
}

async function SimulateForlaniRegister(driver, isFirstTime = true, csvPath = null) {
	const RECORD_GAP_MS    = Number(process.env.FORLANI_RECORD_GAP_MS || 1000);
	const RECORD_LOOP      = envBool("FORLANI_RECORD_LOOP", false);
	const WAIT_AFTER_CLICK = Number(process.env.FORLANI_CLICK_WAIT_MS || 1200);

	let iter = 0;
	do {
		iter++;
		console.log(`\n[FORLANI-REGISTER] Iterazione #${iter}`);

		try { await driver.$(`android=new UiSelector().textContains("REGISTER NEW TEST")`).click(); console.log("Clicked: REGISTER NEW TEST"); }
		catch (e) { try { await driver.$(`android=new UiSelector().textContains("REGISTER")`).click(); console.log("Clicked fallback: REGISTER"); } catch {} }
		await sleep(WAIT_AFTER_CLICK);

		try { await driver.$(`android=new UiSelector().textContains("START NEW TEST")`).click(); console.log("Clicked: START NEW TEST"); }
		catch (e) { try { await driver.$(`android=new UiSelector().textContains("START")`).click(); console.log("Clicked fallback: START"); } catch {} }
		await sleep(WAIT_AFTER_CLICK);

		if (csvPath) {
			console.log(`[FORLANI-REGISTER] Iniezione CSV: ${csvPath}`);
			try {
				await injectExactFromCsv(driver, csvPath);
				console.log("[FORLANI-REGISTER] Iniezione completata.");
			} catch (err) {
				console.error("[FORLANI-REGISTER] Errore durante iniezione:", err?.message || err);
			}
		} else {
			console.log("[FORLANI-REGISTER] csvPath assente: iniezione non eseguita.");
		}

		await sleep(WAIT_AFTER_CLICK);

		try { await driver.$(`android=new UiSelector().textContains("STOP TEST")`).click(); console.log("Clicked: STOP TEST"); }
		catch (e){ try { await driver.$(`android=new UiSelector().textContains("STOP")`).click(); console.log("Clicked fallback: STOP"); } catch {} }
		await sleep(WAIT_AFTER_CLICK);

		if (csvPath) {
			try {
				const notesEl = await driver.$(`android=new UiSelector().textContains("Additional Notes")`);
				const baseName = path.basename(csvPath);
				try { await notesEl.click(); } catch {}
				try { await notesEl.clearValue && notesEl.clearValue(); } catch {}
				try { await notesEl.setValue && notesEl.setValue(baseName); }
				catch { try { await notesEl.addValue && notesEl.addValue(baseName); } catch {} }
				console.log(`Filled Additional Notes with: ${baseName}`);
				await sleep(WAIT_AFTER_CLICK);
			} catch (e) { console.warn('Campo "Additional Notes" non trovato:', e?.message || e); }
		}

		try { await driver.$(`android=new UiSelector().textContains("SAVE TEST")`).click(); console.log("Clicked: SAVE TEST"); }
		catch (e){ try { await driver.$(`android=new UiSelector().textContains("SAVE")`).click(); console.log("Clicked fallback: SAVE"); } catch {} }

		await sleep(RECORD_GAP_MS);
		if (!RECORD_LOOP) break;
		isFirstTime = false;
	} while (true);

	console.log("[FORLANI-REGISTER] Simulazione completata.");
}
async function SimulateForlaniResults(driver, isFirstTime = true, csvPath = null) {
	return SimulateForlaniRegister(driver, isFirstTime, csvPath);
}

async function processBatchCSVFiles(driver, appArg, csvFiles) {
	let processedCount = 0;
	const simulate = selectSimulation(appArg);
	let isFirstCall = true;

	const isVerificationMode = appArg === 'forlani' &&
														 SimulateForlani.currentConfig === 3 &&
														 SimulateForlani.verificationMode === true;

	for (let i = 0; i < csvFiles.length; i++) {
		const csvFile = csvFiles[i];
		console.log(`\n=== FILE ${i + 1}/${csvFiles.length} ===`);
		console.log(`File: ${csvFile.name}`);
		console.log(`Data: ${csvFile.dateFolder}`);

		console.log("== Preparazione UI app ==");
		const simulateHandlesFullFlow = (appArg === 'forlani_register' || appArg === 'forlani_results');
		if (!simulateHandlesFullFlow) { await simulate(driver, isFirstCall); }
		isFirstCall = false;

		let shouldRepeat = true;
		let stopBatch = false;
		while (shouldRepeat) {
			console.log("== Inizio iniezione (timestamp-paced) ==");
			if (simulateHandlesFullFlow) {
				await simulate(driver, false, csvFile.path);
				console.log("== Iniezione (full flow) completata ==");
			} else {
				for (let loop = 0; loop < Math.max(1, LOOP_REPEATS); loop++) {
					await injectExactFromCsv(driver, csvFile.path);
					if (loop < LOOP_REPEATS - 1 && LOOP_GAP_MS > 0) await sleep(LOOP_GAP_MS);
				}
				console.log("== Iniezione completata ==");
			}

			const userInput = await askForSteps(csvFile.name);
			if (userInput === 'r') {
				console.log("Ripetizione injection richiesta...\n");
				if (simulateHandlesFullFlow) {
					await simulate(driver, false, csvFile.path);
				} else {
					for (let loop = 0; loop < Math.max(1, LOOP_REPEATS); loop++) {
						await injectExactFromCsv(driver, csvFile.path);
						if (loop < LOOP_REPEATS - 1 && LOOP_GAP_MS > 0) await sleep(LOOP_GAP_MS);
					}
				}
				await sleep(1000);
				shouldRepeat = true;
			} else if (userInput === 'n') {
				console.log("Nessun salvataggio per questo file.");
				shouldRepeat = false;
			} else if (userInput === 's') {
				console.log("Batch interrotto dall'utente.");
				stopBatch = true;
				shouldRepeat = false;
			} else {
				const stepsCount = parseInt(userInput);
				if (!Number.isFinite(stepsCount) || stepsCount < 0) {
					console.log("Numero non valido. Non salvando risultati.");
				} else {
					if (appArg !== 'forlani_register') {
						if (isVerificationMode) {
							const batchSteps = await askBatchSteps(csvFile.name);
							if (batchSteps != null) saveVerificationResult(csvFile.name, stepsCount, batchSteps);
						}
						saveStepsResult(appArg, csvFile.name, csvFile.path, stepsCount);
						processedCount++;
					} else {
						console.log("Modalità forlani_register: risultato non salvato.");
					}
				}
				shouldRepeat = false;
			}
		}

		if (stopBatch) break;

		if (i < csvFiles.length - 1) {
			const cont = await askContinueBatch();
			if (!cont) { console.log("Elaborazione batch interrotta dall'utente."); break; }
		}
	}

	console.log(`\n=== RIEPILOGO BATCH ===`);
	console.log(`File processati: ${processedCount}`);
	console.log(`File totali: ${csvFiles.length}`);
}

function askContinueBatch() {
	return new Promise((resolve) => {
		const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
		rl.question("Vuoi continuare con l'injection del prossimo file? (y/n): ", (answer) => {
			rl.close();
			resolve((answer||'').toLowerCase().trim().startsWith('y'));
		});
	});
}
function askForlaniConfiguration() {
	return new Promise((resolve) => {
		const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
		console.log("\n=== SELEZIONE CONFIGURAZIONE FORLANI ===");
		console.log("1. Peak + Butterworth Filter");
		console.log("2. Peak + Intersection + Low-Pass Filter 10 Hz");
		console.log("3. Peak + Low-Pass Filter");
		console.log("4. Peak + Intersection + Low-Pass Filter 2%");
		console.log("5. Peak + Time Filtering + Low-Pass Filter 10 Hz");
		console.log("6. Time Filtering + Peak + Butterworth Filter");
		rl.question("Seleziona la configurazione (1-6): ", (answer) => {
			rl.close();
			const n = parseInt((answer||'').trim());
			resolve(n>=1 && n<=6 ? n : 1);
		});
	});
}
function askVerificationMode() {
	return new Promise((resolve) => {
		const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
		console.log("\n=== MODALITÀ VERIFICA ===");
		rl.question("Vuoi attivare la modalità di verifica? (y/n): ", (answer) => {
			rl.close();
			resolve((answer||'').trim().toLowerCase().startsWith('y'));
		});
	});
}
function askBatchSteps(fileName) {
	return new Promise((resolve) => {
		const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
		console.log(`File: ${fileName}`);
		rl.question("Inserisci il numero di passi in BATCH: ", (answer) => {
			rl.close();
			const n = parseInt((answer||'').trim());
			resolve(Number.isFinite(n) ? n : null);
		});
	});
}
function askForSteps(fileName) {
	return new Promise((resolve) => {
		const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
		console.log(`File: ${fileName}`);
		console.log("Inserisci il numero di passi oppure:");
		console.log("'r' = ripeti iniezione, 'n' = non salvare, 's' = ferma batch");
		rl.question("Scelta: ", (answer) => {
			rl.close();
			const a = (answer||'').trim().toLowerCase();
			if (['r','n','s'].includes(a)) return resolve(a);
			resolve(a);
		});
	});
}
function assertAxisSettings() {
	if (!/^[XYZ]{3}$/.test(AXIS_MAP))  throw new Error(`AXIS_MAP non valido: "${AXIS_MAP}" (atteso: es. XYZ, ZXY)`);
	if (!/^[+\-]{3}$/.test(AXIS_SIGN)) throw new Error(`AXIS_SIGN non valido: "${AXIS_SIGN}" (atteso: tre simboli +/-, es. +++)`);
}
function isFileAlreadyProcessed(appName, csvFileName) {
	if (appName === 'forlani_register') return false;
	if (appName === 'forlani' && SimulateForlani.currentConfig) {
		const nameByCfg = {
			1:'results_forlani_peak_butterworth.csv',
			2:'results_forlani_peak_intersection_low_pass_10hz.csv',
			3:'results_forlani_peak_low_pass.csv',
			4:'results_forlani_peak_intersection_low_pass_2percent.csv',
			5:'results_forlani_peak_time_filtering_low_pass_10hz.csv',
			6:'results_forlani_time_filtering_peak_butterworth.csv'
		}[SimulateForlani.currentConfig];
		const fp = path.join(__dirname, nameByCfg);
		if (!fs.existsSync(fp)) return false;
		const lines = fs.readFileSync(fp, "utf8").split("\n").slice(1);
		return lines.some(l => l && l.split(",")[1]?.replace(/"/g,'').trim() === csvFileName);
	}
	try {
		const resultsFile = getAppResultsFile(appName);
		if (!fs.existsSync(resultsFile)) return false;
		const lines = fs.readFileSync(resultsFile, "utf8").split("\n").slice(1);
		return lines.some(l => l && l.split(",")[1]?.replace(/"/g,'').trim() === csvFileName);
	} catch { return false; }
}

async function injectBatchPythonMode(driver, appArg) {
	if(appArg !== 'reina') {
		console.error("Modalità non implementata per questa app");
		process.exit(2);
	}
	let injectionCount = 0;
	let iterationsCount = 1;
	const simulate = selectSimulation(appArg);

	for(const magnitude of ['Lower', 'Normal', 'Higher']) {
		for(const injectionFrequency of [50, 100, 200, 500, 1000, 10000]) {
			for(const sensorDelay of ['DELAY-GAME', 'DELAY-FASTEST']) {
				for(const iteration=0; iteration<iterationsCount; iteration++) {
					Console.log(`iniezione: ${magnitude}_${injectionFrequency}_${sensorDelay}_send#_${iteration}`);
					SimulateReina(driver, magnitude, injectionFrequency, sensorDelay);
				}
				injectionCount++;
			}
		}
	}

	console.log(`\n=== INIEZIONI COMPLETATE ===`);
	console.log(`configurazioni totali: ${injectionCount}`);
	console.log(`iterazioni: ${iterationsCount}`);
}

async function main() {
	assertAxisSettings();

	const appArg = (process.argv[2] || "").toLowerCase();
	const mode = process.argv[3];

	if (!appArg) {
		console.log("Uso:");
		console.log("  File locale:   node inject_sensors.js <app> <file.csv>");
		console.log("  Firebase:      node inject_sensors.js <app> firebase");
		console.log("  Python Script: node inject_sensors.js reina python");
		console.log("app ∈ { run, tayutau, accupedo, walklogger, forlani, forlani_register, forlani_results, motiontracker, reina }");
		process.exit(2);
	}

	const app = selectApp(appArg);
	const isPythonMode = mode === 'python';
	const isFirebaseMode = mode === 'firebase';
	let csvFiles = [];

	if (isPythonMode) {
		// injection fully handled by python script
	} else if (isFirebaseMode) {
		console.log("=== MODALITÀ FIREBASE ===");
		csvFiles = await selectDateAndDownloadCSVs(appArg);
		if (csvFiles.length === 0) { console.log("Nessun file CSV da processare. Uscita..."); process.exit(1); }
	} else {
		const csvArg = mode;
		if (!csvArg) { console.log("Specificare il file CSV o 'firebase'"); process.exit(2); }
		const csvPath = isAbsolute(csvArg) ? csvArg : (`./${csvArg}`);
		if (!fs.existsSync(csvPath)) { console.error("File CSV non trovato:", csvPath); process.exit(3); }
		if (isFileAlreadyProcessed(appArg, path.basename(csvPath))) { console.log("File già processato. Uscita..."); process.exit(0); }
		csvFiles = [{ name: path.basename(csvPath), path: csvPath, dateFolder: 'local' }];
	}

	const opts = {
		hostname: process.env.APPIUM_HOST || "127.0.0.1",
		port: Number(process.env.APPIUM_PORT || 4723),
		path: process.env.APPIUM_BASE_PATH || "/",
		capabilities: {
			platformName: "Android",
			"appium:deviceName": process.env.DEVICE_NAME || "Android Emulator",
			"appium:avd": process.env.AVD_NAME || undefined,
			"appium:avdLaunchTimeout": Number(process.env.AVD_LAUNCH_TIMEOUT || 240000),
			"appium:app": app,
			"appium:automationName": process.env.AUTOMATION_NAME || "UiAutomator2",
			"appium:newCommandTimeout": Number(process.env.NEW_COMMAND_TIMEOUT || 600),
			"appium:autoGrantPermissions": envBool("AUTO_GRANT_PERMISSIONS", true),
			"appium:noReset": envBool("NO_RESET", true),
			"appium:allowInsecure": ["emulator_console"]
		}
	};
	
	console.log("== Avvio sessione ==");
	console.log("APK:", app);
	if(isPythonMode)
		console.log("Modalità: Script Python");
	else{
		console.log(`Modalità: ${isFirebaseMode ? 'Firebase Storage' : 'File locale'}`);
		console.log(`File da processare: ${csvFiles.length}`);
	}

	const driver = await wdio.remote(opts);

	try {
		if(isPythonMode){
			await injectBatchPythonMode(driver, appArg);
		}else{
			await ensureEmulator(driver);
			await processBatchCSVFiles(driver, appArg, csvFiles);
		}
	} finally {
		try { await sleep(500); await driver.deleteSession(); }
		catch (e) { console.warn("Chiusura sessione:", e?.message || e); }

		if (isFirebaseMode && fs.existsSync(path.join(__dirname, 'temp_csv'))) {
			try { fs.rmSync(path.join(__dirname, 'temp_csv'), { recursive: true, force: true }); console.log("File temporanei puliti."); }
			catch (e) { console.warn("Errore nella pulizia file temporanei:", e.message); }
		}
	}
}

main().catch((err) => {
	console.error("Errore:", err?.stack || err?.message || err);
	process.exit(1);
});
