PRAGMA foreign_keys=ON;
CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE components(
 id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE aliases(
 component_id INTEGER NOT NULL REFERENCES components(id) ON DELETE CASCADE,
 value TEXT NOT NULL, normalized TEXT NOT NULL, PRIMARY KEY(component_id, normalized)
);
CREATE INDEX aliases_search ON aliases(normalized);
CREATE TABLE prices(
 component_id INTEGER NOT NULL REFERENCES components(id) ON DELETE CASCADE,
 period TEXT NOT NULL, package_price REAL NOT NULL CHECK(package_price>=0),
 volume_liters REAL NOT NULL CHECK(volume_liters>0), grams_per_liter REAL NOT NULL CHECK(grams_per_liter>0),
 source TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(component_id,period)
);
CREATE TABLE recipes(
 id INTEGER PRIMARY KEY, name TEXT NOT NULL DEFAULT '', color_code TEXT NOT NULL DEFAULT '',
 brand TEXT NOT NULL DEFAULT '', vehicle TEXT NOT NULL DEFAULT '', work_order TEXT NOT NULL DEFAULT '',
 comment TEXT NOT NULL DEFAULT '', manufactured_on TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, source TEXT NOT NULL,
 snapshot_total REAL NOT NULL, snapshot_mass REAL NOT NULL CHECK(snapshot_mass>0),
 revision INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX recipes_color ON recipes(color_code);
CREATE INDEX recipes_created ON recipes(created_at);
CREATE TABLE recipe_lines(
 recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
 position INTEGER NOT NULL, component_id INTEGER NOT NULL REFERENCES components(id) ON DELETE RESTRICT,
 mass_expression TEXT NOT NULL, mass_grams REAL NOT NULL CHECK(mass_grams>0),
 snapshot_price REAL NOT NULL, snapshot_period TEXT NOT NULL,
 PRIMARY KEY(recipe_id,position)
);
PRAGMA user_version=1;
