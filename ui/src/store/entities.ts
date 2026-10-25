export interface EntityMap<T> {
  entities: Record<string, T>;
  ids: string[];
}

/** Replace the collection with `items`, preserving array order in `ids`. */
export function setAll<T extends { id: string }>(map: EntityMap<T>, items: T[]): void {
  map.entities = {};
  map.ids = [];
  for (const item of items) {
    map.entities[item.id] = item;
    map.ids.push(item.id);
  }
}
