// Prints the temporary audit token from the private state sheet (read with the service account).
import { JWT } from "google-auth-library";
const k = JSON.parse(process.env.GOOGLE_SERVICE_ACCOUNT_JSON);
const jwt = new JWT({ email: k.client_email, key: k.private_key, scopes: ["https://www.googleapis.com/auth/spreadsheets.readonly"] });
const { token } = await jwt.getAccessToken();
const r = await fetch("https://sheets.googleapis.com/v4/spreadsheets/1LrpaLYWZp3OJfMF8aNtNQM6JByy4QpQU-PAKuE_VVVo/values/Audit!A1", { headers: { Authorization: `Bearer ${token}` } });
console.log(((await r.json()).values || [[""]])[0][0]);
