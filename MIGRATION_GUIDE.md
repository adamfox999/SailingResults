# QE Code System Removal - Migration Guide

## Overview

The QE (Quick Entry) code system has been removed. The system now uses Entry IDs that are automatically generated and scoped to series.

## Changes Made

### Backend Changes

#### 1. Entry Model (`swsc_core/entry.py`)
- **Removed**: `qe` field (reference to QE object)
- **Added**: 
  - `entry_id`: Unique identifier for competitor within series
  - `helm`: Helm name (direct field)
  - `crew`: Crew name (direct field)
  - `dinghy`: Boat class name (direct field)
  - `py`: Portsmouth Yardstick number (direct field)
  - `personal`: Personal handicap (direct field, 0 = no personal handicap)

#### 2. Race Model (`swsc_core/race.py`)
- **Removed**: `qes` parameter from `__init__`
- **Updated**: PyRow and PersonalRow to use `entry_id` instead of `qe_code`
- **Changed**: Summary header from "QE   Helm..." to "ID    Helm..."

#### 3. DataStore (`swsc_core/loader.py`)
- **Removed**: `load_qes()` method
- **Removed**: `sources()` method (no longer needed)
- **Simplified**: Only loads handicaps from Supabase
- **Kept**: CSV fallback for handicaps (but no QE file support)

#### 4. API Endpoints (`app/main.py`)
- **Removed**: `base_qes()` function
- **Removed**: `_match_qe()` helper function

##### `/reference` endpoint:
- **Removed**: `qeCodes` array
- **Removed**: `people` array
- **Kept**: `classes`, `classOptions`, `finCodes`

##### `/score` endpoint:
- **Entry Payload Changes**:
  - Removed: `qe` field
  - Added: `entry_id` (optional - auto-generated if not provided)
  - Added: `personal` field (personal handicap)
  
- **Entry ID Generation Logic**:
  ```
  - If entry_id provided: use it
  - If not provided: generate from series name + sequence number
  - Format: {SERIES_PREFIX}{NUM} (e.g., "AUTU001", "AUTU002")
  - Same competitor (helm+crew+dinghy) gets same entry_id within session
  ```

- **Response Changes**:
  - PyRowModel: `qe` → `entryId`
  - PersonalRowModel: Added `entryId` field

### Entry ID Scoping

**Current Implementation** (Single Race):
- Entry IDs generated per scoring request
- Format: `{SERIES_PREFIX}{SEQUENCE}`
- Same competitor gets same ID within one score() call

**Future Implementation** (Series Support):
- Entry IDs should be persistent across races in a series
- Requires database/storage layer to track:
  - Series ID
  - Competitor details (helm, crew, dinghy)
  - Assigned entry_id
- When scoring race in existing series:
  - Look up existing entry_id for competitor
  - Reuse if found, generate new if not

## Frontend Changes Needed

### 1. Remove QE Code Input
- Remove QE code dropdown/input field
- Remove QE code lookup logic
- Remove `qeIndex` and `qeOptions` state

### 2. Update Entry Form
Current fields (keep these):
- ✓ Helm name (text input)
- ✓ Crew name (text input)
- ✓ Dinghy class (dropdown with autocomplete)
- ✓ Laps (number)
- ✓ Time (seconds)
- ✓ Finish code (dropdown)

New/Modified fields:
- Add: Personal handicap (number input, default 0)
- Add: Entry ID (hidden/readonly - will be in response)

### 3. Update TypeScript Interfaces

```typescript
// Remove
interface ReferenceQE {
  code: string;
  helm: string;
  crew: string;
  dinghy: string;
  py: number;
  personal: number;
}

// Update
interface ReferenceData {
  classes: { [key: string]: number };
  classOptions: ClassOption[];
  finCodes: string[];
  // REMOVED: qeCodes, people
}

interface EntryPayload {
  entryId?: string;  // Changed from qe
  helm: string;
  crew: string;
  dinghy: string;
  personal: number;  // New field
  laps?: number;
  timeSeconds?: number;
  finCode?: string;
}

interface PyRow {
  entryId: string;  // Changed from qe
  helm: string;
  crew: string;
  dinghy: string;
  py: number;
  laps: number;
  timeSeconds: number;
  corrected?: number;
  rank?: number;
  finCode: string;
}

interface PersonalRow {
  entryId: string;  // New field
  helm: string;
  crew: string;
  personalHandicap: number;
  corrected?: number;
  rank?: number;
}
```

### 4. Remove QE-related UI Code

#### In `page.tsx`:
```typescript
// REMOVE these:
const qeIndex = useMemo(...)
const qeOptions = useMemo(...)

// REMOVE QE autocomplete/dropdown
<input list="qe-codes" ... />
<datalist id="qe-codes">...</datalist>

// REMOVE auto-fill from QE selection
const handleQeChange = (selectedQe: string) => { ... }
```

### 5. Update Results Display

- Change "QE" column to "Entry ID" in results tables
- Update any references to `row.qe` to `row.entryId`
- Remove "QE Codes" from reference data displays

## Testing

### Backend Tests
```bash
cd web/backend
.venv\Scripts\python.exe test_reference.py
```

Expected output:
- Classes: 297
- Class Options: 297
- Fin Codes: 6
- No errors

### API Test
```bash
curl http://127.0.0.1:8000/reference
```

Should return:
```json
{
  "classes": {...},
  "classOptions": [...],
  "finCodes": ["", "DNF", "DNC", "OCS", "RET", "DSQ"]
}
```

### Score Endpoint Test
```bash
curl -X POST http://127.0.0.1:8000/score \
  -H "Content-Type: application/json" \
  -d '{
    "metadata": {
      "series": "Autumn",
      "race": "1",
      "raceOfficer": "Test",
      "date": "2025-10-04"
    },
    "entries": [
      {
        "helm": "John Doe",
        "crew": "Jane Smith",
        "dinghy": "RS200",
        "personal": 0,
        "laps": 5,
        "timeSeconds": 3600
      }
    ]
  }'
```

## Migration Steps

1. ✅ Backend updated - Entry, Race, DataStore, API endpoints
2. ✅ Backend tested - reference endpoint working
3. ⏳ Update frontend TypeScript interfaces
4. ⏳ Remove QE code input from entry form
5. ⏳ Add personal handicap input field
6. ⏳ Update results display to show Entry ID
7. ⏳ Test full workflow: entry → score → results
8. ⏳ (Future) Add series database for persistent entry IDs

## Benefits

✨ **Simplified Data Entry**:
- No need to remember QE codes
- Direct input of helm, crew, boat
- Auto-generation of IDs

✨ **Cleaner Codebase**:
- Removed QE file loading
- Removed QE matching logic
- Reduced API response size

✨ **Flexible Personal Handicaps**:
- Can be set per-entry
- No need to update QE files

✨ **Series Support Ready**:
- Entry ID system designed for series tracking
- Foundation for multi-race series scoring

## Notes

- Entry ID format is flexible - can be changed to UUID or other schemes
- Personal handicaps are optional (default 0)
- Supabase still used for boat class handicaps
- CSV fallback still available for handicaps (not for QE codes)
