import http from 'k6/http';
import { sleep, check } from 'k6';
import { fail } from 'k6';

export const options = {
  vus: 10,
  duration: '30s',
};

const BEARER_TOKEN = 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6Im9OV0xsU0NtaU1mRFR0dFpUWnpqVyJ9.eyJodHRwczovL2hhc3VyYS5pby9qd3QvY2xhaW1zIjp7IngtaGFzdXJhLWFsbG93ZWQtcm9sZXMiOlsidXNlciJdLCJ4LWhhc3VyYS1kZWZhdWx0LXJvbGUiOiJ1c2VyIiwieC1oYXN1cmEtdXNlci1pZCI6ImVtYWlsfDY1ZDUxZjlmNzhjMTdlZTIxZTc5MDdmYiJ9LCJpc3MiOiJodHRwczovL296cXIuYXUuYXV0aDAuY29tLyIsImF1ZCI6ImYzRWU4aG9YM3RwU2RyazQzOGxlTEVUajc5bVNxc3g5IiwiaWF0IjoxNzA5MTUxOTQ1LCJleHAiOjE3MTAwMTU5NDQsInN1YiI6ImVtYWlsfDY1ZDUxZjlmNzhjMTdlZTIxZTc5MDdmYiIsInNpZCI6IjhxOC1fcUE2MjF1RU96bGFtNnI2TERucGE1YVdwQTdrIiwibm9uY2UiOiIxMjMifQ.aK6AHv7_SqFJ2B238ozvdQlEn6EGpFBQCGalrOiRtFVFkpIT_repZRutELDnd-vevc3OfuFFKb33TXi_ZKl3bu8c9WfbxM_UVoRJR5t7R_3hBxPIfaIZ20kn8R3s_93bFXWq5PrB_SmveALjnRsgkF2bppSyOcx2l5922b34udQR9k0aw6oD8PQ-WjvKsydQoMGsEHuKqlvUEqdt1wQGXUAXSMhPeYAGDu_nk-rfk4t_4nV03r0jXCexX6xfMZWgTTkyti-oA6JzJeADR_OpLIaIjiYJLQgoVjInzB7X0X_hwSZTvF2Nw9EHazaqKkNOrpXnBOXYejfM5rYeuSNEbA';


export default function() {
  const url = 'https://hasura.ozqr.dev/v1/graphql'; // Replace with your GraphQL endpoint
  const params = {
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${BEARER_TOKEN}`,
    },
  };

  const requestBody = {
    query: `
      mutation MyMutation($accountID: uuid!, $amountTransfer: float8!, $pan: String!, $expiry: String!, $permanentCVV: smallint!) {
        UserPayWithStaticQRCode(accountID: $accountID, amountTransfer: $amountTransfer, expiry: $expiry, permanentCVV: $permanentCVV, pan: $pan) {
          receiverName
          invoiceNumber
          datetime
          amount
        }
      }
    `,
    variables: {
      accountID: "9d33d123-3a48-4fef-a575-1108ca815fe6",
      amountTransfer: 0.3,
      permanentCVV: 657,
      pan: "4716790672639435",
      expiry: "05/28"
    },
  };

  const res = http.post(url, JSON.stringify(requestBody), params);
  
  const checkRes = check(res, {
    'is status 200': (r) => r.status === 200,
    'is no error in response': (r) => !JSON.parse(r.body).errors,
  });

  if (!checkRes) {
    console.error(`Request failed. Status: ${res.status}, Body: ${res.body}`);
    fail('Test failed due to unsuccessful GraphQL mutation.');
  }

  sleep(1);
}
