const express = require('express');
const bodyParser = require('body-parser');
const ngrok = require('ngrok');
const fs = require('fs');

const app = express();
const port = 3000;

// Use the built-in JSON parser middleware
app.use(bodyParser.json());

// Array to store incoming JSON data
let storedData = [];

// Endpoint to receive JSON via POST
app.post('/', (req, res) => {
  const jsonData = req.body;
  console.log('Received JSON:', jsonData);

  // Store data in memory
  storedData.push(jsonData);

  // Optionally, store the updated data in a file (data.json)
  fs.writeFileSync('data.json', JSON.stringify(storedData, null, 2));
  
  res.status(200).send('Data received and stored.');
});

// Set your ngrok authtoken (replace <your-authtoken> with your actual token)
ngrok.authtoken('2vF6IAJElqcu0kcdtOmmWPeNymR_69xausyWKehkPfzYB3ik1');

app.listen(port, async () => {
  console.log(`Server is running on http://localhost:${port}`);
  
  try {
    const url = await ngrok.connect(port);
    console.log(`Ngrok tunnel established at: ${url}`);
  } catch (err) {
    console.error('Error establishing ngrok tunnel:', err);
  }
});