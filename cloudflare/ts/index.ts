import Cloudflare from 'cloudflare';

// Initialize the Cloudflare client with your credentials
const cloudflare = new Cloudflare({
  apiEmail: 'accounts@kolossusdigital.com.au',
  apiKey: '2be1be98e6d38c0856c6a3403dad9d8ce5ad1',
});

async function main() {
  try {
    // Create a new zone
    const zone = await cloudflare.zones.create({
      account: { id: '84923d37466e678deb52e92e49c10c0d' },
      name: 'kolossus.com.au',
      type: 'full',
    });

    console.log('Zone ID:', zone.id);
  } catch (error) {
    console.error('Error creating zone:', error);
  }
}

main();
