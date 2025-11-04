# scripts/check_gcs.py
# Simple diagnostic for GCS credentials and bucket access
from dotenv import load_dotenv
import os
import sys

load_dotenv('.env', override=True)

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

print('ENV:')
print('  GCS_BUCKET_NAME =', repr(os.getenv('GCS_BUCKET_NAME')))
print('  GOOGLE_APPLICATION_CREDENTIALS =', repr(os.getenv('GOOGLE_APPLICATION_CREDENTIALS')))
print('  SKIP_GCS_UPLOAD =', repr(os.getenv('SKIP_GCS_UPLOAD')))

# check file exists
gac = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
if gac:
    print('  GAC file exists:', os.path.exists(gac))
else:
    print('  GAC not set')

# google.auth.default
try:
    import google.auth
    creds, project = google.auth.default()
    email = getattr(creds, 'service_account_email', None) or getattr(creds, 'client_email', None)
    print('google.auth.default -> project:', project, 'cred_type:', type(creds).__name__, 'email:', email)
except Exception as e:
    eprint('google.auth.default() FAILED:', e)

# storage client + bucket check
try:
    from google.cloud import storage
    client = storage.Client()
    print('storage.Client() project:', client.project)
    bucket_name = os.getenv('GCS_BUCKET_NAME')
    if bucket_name:
        try:
            b = client.lookup_bucket(bucket_name)
            if b is None:
                print('lookup_bucket -> None (bucket missing or not accessible)')
            else:
                print('lookup_bucket -> bucket found')
                try:
                    print('bucket.exists():', b.exists())
                except Exception as ex:
                    eprint('bucket.exists() check FAILED:', ex)
        except Exception as e:
            eprint('client.lookup_bucket FAILED:', e)
    else:
        print('no GCS_BUCKET_NAME set')
except Exception as e:
    eprint('google.cloud.storage check FAILED:', e)
