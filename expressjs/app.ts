import express from 'express';
import routes from './routes'; // Adjust the path as necessary

import { rootCertificates } from 'tls';
const app = express();
const port = 3000;


app.use(express.json());
app.use('/api', routes); // Mount your routes under /api prefix

app.listen(port, () => { console.log(`server is running on http:localhost:${port}`)} )
