# World-generation service

This service converts a geographic selection into a deterministic mission
package.

Internal stages:

- geographic data acquisition and attribution;
- projection and feature simplification;
- OpenRA terrain compilation;
- spawn, resource, and objective design;
- story and Lua mission generation;
- playability validation and repair;
- packaging and manifest generation.

Each stage is independently testable and cacheable.
