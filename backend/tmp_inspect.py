import os

os.environ['SUPABASE_URL'] = 'https://fazawdwokaahuslisksn.supabase.co'
os.environ['SUPABASE_SERVICE_ROLE_KEY'] = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZhemF3ZHdva2FhaHVzbGlza3NuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTk0OTI4MjcsImV4cCI6MjA3NTA2ODgyN30.BFcrU9g4_8RaerZG-JwnA7uA1fyneQjYya3RWWJJa28'

from swsc_core.loader import DataStore

store = DataStore()
store.load_handicaps()
options = store.class_display_options()
print('Total options:', len(options))

print('\nAll SPRINT/DART options:')
for key, label in options:
    if 'SPRINT' in label or 'DART' in label:
        print(f'  {key!r} -> {label!r}')

print('\nChecking handicaps dict:')
handicaps = store._handicaps_cache
print('  "SPRINT 15" in handicaps:', 'SPRINT 15' in handicaps)
print('  "DART 15" in handicaps:', 'DART 15' in handicaps)
print('  "DART 15 / SPRINT 15" in handicaps:', 'DART 15 / SPRINT 15' in handicaps)