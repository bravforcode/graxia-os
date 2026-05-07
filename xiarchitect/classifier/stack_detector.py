"""
xiarchitect.classifier.stack_detector — Builds StackSummary from scanned files
"""

import json
import re
from pathlib import Path
from typing import Dict, List

from ..core.logger import get_logger
from ..core.types import DetectedTechnology, Evidence, EvidenceType, ScannedFile, StackSummary

logger = get_logger(__name__)


class StackDetector:
    """Detects technology stack from scanned files"""
    
    def __init__(self):
        """Initialize stack detector"""
        self.detected: Dict[str, DetectedTechnology] = {}
    
    def detect(self, files: List[ScannedFile]) -> StackSummary:
        """
        Detect stack from scanned files.
        
        Args:
            files: List of scanned files
        
        Returns:
            Complete stack summary
        """
        logger.info("Detecting technology stack...")
        
        self.detected = {}
        
        # Detect from various sources
        for file in files:
            self._detect_from_file(file)
        
        # Build stack summary
        stack = self._build_stack_summary()
        
        logger.info(f"Stack detection complete: {len(self.detected)} technologies found")
        
        return stack
    
    def _detect_from_file(self, file: ScannedFile):
        """Detect technologies from a single file"""
        
        # requirements.txt
        if file.relative_path.endswith("requirements.txt") and file.content:
            self._parse_requirements_txt(file)
        
        # package.json
        elif file.relative_path.endswith("package.json") and file.content:
            self._parse_package_json(file)
        
        # pyproject.toml
        elif file.relative_path.endswith("pyproject.toml") and file.content:
            self._parse_pyproject_toml(file)
        
        # docker-compose.yml
        elif "docker-compose" in file.relative_path and file.content:
            self._parse_docker_compose(file)
        
        # Dockerfile
        elif "Dockerfile" in file.relative_path and file.content:
            self._parse_dockerfile(file)
        
        # Python files
        elif file.extension == ".py" and file.content:
            self._detect_python_frameworks(file)
        
        # TypeScript/JavaScript files
        elif file.extension in [".ts", ".tsx", ".js", ".jsx"] and file.content:
            self._detect_js_frameworks(file)
    
    def _parse_requirements_txt(self, file: ScannedFile):
        """Parse requirements.txt"""
        if not file.content:
            return
        
        for line in file.content.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            # Parse package==version or package>=version
            match = re.match(r"^([a-zA-Z0-9_-]+)([>=<~!]+)?([0-9.]+)?", line)
            if match:
                package = match.group(1).lower()
                version = match.group(3) if match.group(3) else None
                
                self._add_technology(
                    name=package,
                    version=version,
                    category="backend",
                    confidence=0.95,
                    evidence=Evidence(
                        file=file.relative_path,
                        line=None,
                        reason=f"Listed in requirements.txt",
                        confidence=0.95,
                        type=EvidenceType.PACKAGE_JSON_DEPENDENCY,
                    )
                )
    
    def _parse_package_json(self, file: ScannedFile):
        """Parse package.json"""
        if not file.content:
            return
        
        try:
            data = json.loads(file.content)
            
            # Parse dependencies
            for dep_type in ["dependencies", "devDependencies"]:
                if dep_type in data:
                    for package, version in data[dep_type].items():
                        self._add_technology(
                            name=package,
                            version=version.lstrip("^~>=<"),
                            category="frontend" if dep_type == "dependencies" else "testing",
                            confidence=0.90,
                            evidence=Evidence(
                                file=file.relative_path,
                                reason=f"Listed in package.json {dep_type}",
                                confidence=0.90,
                                type=EvidenceType.PACKAGE_JSON_DEPENDENCY,
                            )
                        )
        except json.JSONDecodeError:
            pass
    
    def _parse_pyproject_toml(self, file: ScannedFile):
        """Parse pyproject.toml"""
        if not file.content:
            return
        
        # Simple regex-based parsing (not full TOML parser)
        for line in file.content.split("\n"):
            # Match: package = "^1.2.3" or package = ">=1.2.3"
            match = re.match(r'^\s*"?([a-zA-Z0-9_-]+)"?\s*=\s*"([^"]+)"', line)
            if match:
                package = match.group(1).lower()
                version = match.group(2).lstrip("^~>=<")
                
                self._add_technology(
                    name=package,
                    version=version,
                    category="backend",
                    confidence=0.90,
                    evidence=Evidence(
                        file=file.relative_path,
                        reason="Listed in pyproject.toml",
                        confidence=0.90,
                        type=EvidenceType.PACKAGE_JSON_DEPENDENCY,
                    )
                )
    
    def _parse_docker_compose(self, file: ScannedFile):
        """Parse docker-compose.yml"""
        if not file.content:
            return
        
        # Detect services
        services_match = re.search(r"services:", file.content)
        if services_match:
            # Look for common service images
            if "postgres" in file.content.lower():
                self._add_technology(
                    name="PostgreSQL",
                    category="database",
                    confidence=0.97,
                    evidence=Evidence(
                        file=file.relative_path,
                        reason="PostgreSQL service in docker-compose",
                        confidence=0.97,
                        type=EvidenceType.DOCKER_SERVICE_DECLARATION,
                    )
                )
            
            if "redis" in file.content.lower():
                self._add_technology(
                    name="Redis",
                    category="cache",
                    confidence=0.97,
                    evidence=Evidence(
                        file=file.relative_path,
                        reason="Redis service in docker-compose",
                        confidence=0.97,
                        type=EvidenceType.DOCKER_SERVICE_DECLARATION,
                    )
                )
            
            if "celery" in file.content.lower():
                self._add_technology(
                    name="Celery",
                    category="workers",
                    confidence=0.95,
                    evidence=Evidence(
                        file=file.relative_path,
                        reason="Celery worker in docker-compose",
                        confidence=0.95,
                        type=EvidenceType.DOCKER_SERVICE_DECLARATION,
                    )
                )
    
    def _parse_dockerfile(self, file: ScannedFile):
        """Parse Dockerfile"""
        if not file.content:
            return
        
        # Detect base images
        for line in file.content.split("\n"):
            if line.strip().startswith("FROM"):
                image = line.split()[1] if len(line.split()) > 1 else ""
                
                if "python" in image.lower():
                    version_match = re.search(r"python:([0-9.]+)", image.lower())
                    version = version_match.group(1) if version_match else None
                    
                    self._add_technology(
                        name="Python",
                        version=version,
                        category="languages",
                        confidence=0.95,
                        evidence=Evidence(
                            file=file.relative_path,
                            reason=f"Python base image in Dockerfile",
                            confidence=0.95,
                            type=EvidenceType.DOCKER_SERVICE_DECLARATION,
                        )
                    )
                
                elif "node" in image.lower():
                    version_match = re.search(r"node:([0-9.]+)", image.lower())
                    version = version_match.group(1) if version_match else None
                    
                    self._add_technology(
                        name="Node.js",
                        version=version,
                        category="languages",
                        confidence=0.95,
                        evidence=Evidence(
                            file=file.relative_path,
                            reason="Node.js base image in Dockerfile",
                            confidence=0.95,
                            type=EvidenceType.DOCKER_SERVICE_DECLARATION,
                        )
                    )
    
    def _detect_python_frameworks(self, file: ScannedFile):
        """Detect Python frameworks from code"""
        if not file.content:
            return
        
        # FastAPI
        if "from fastapi import" in file.content or "FastAPI()" in file.content:
            self._add_technology(
                name="FastAPI",
                category="backend",
                confidence=0.95,
                evidence=Evidence(
                    file=file.relative_path,
                    reason="FastAPI import detected",
                    confidence=0.95,
                    type=EvidenceType.EXPLICIT_IMPORT,
                )
            )
        
        # SQLAlchemy
        if "from sqlalchemy" in file.content:
            self._add_technology(
                name="SQLAlchemy",
                category="database",
                confidence=0.90,
                evidence=Evidence(
                    file=file.relative_path,
                    reason="SQLAlchemy import detected",
                    confidence=0.90,
                    type=EvidenceType.EXPLICIT_IMPORT,
                )
            )
        
        # Celery
        if "from celery import" in file.content or "@celery.task" in file.content:
            self._add_technology(
                name="Celery",
                category="workers",
                confidence=0.95,
                evidence=Evidence(
                    file=file.relative_path,
                    reason="Celery import detected",
                    confidence=0.95,
                    type=EvidenceType.EXPLICIT_IMPORT,
                )
            )
        
        # Stripe
        if "import stripe" in file.content:
            self._add_technology(
                name="Stripe",
                category="external",
                confidence=0.95,
                evidence=Evidence(
                    file=file.relative_path,
                    reason="Stripe import detected",
                    confidence=0.95,
                    type=EvidenceType.EXPLICIT_IMPORT,
                )
            )
    
    def _detect_js_frameworks(self, file: ScannedFile):
        """Detect JavaScript/TypeScript frameworks"""
        if not file.content:
            return
        
        # React
        if "from 'react'" in file.content or 'from "react"' in file.content:
            self._add_technology(
                name="React",
                category="frontend",
                confidence=0.95,
                evidence=Evidence(
                    file=file.relative_path,
                    reason="React import detected",
                    confidence=0.95,
                    type=EvidenceType.EXPLICIT_IMPORT,
                )
            )
        
        # Next.js
        if "from 'next" in file.content or 'from "next' in file.content:
            self._add_technology(
                name="Next.js",
                category="frontend",
                confidence=0.95,
                evidence=Evidence(
                    file=file.relative_path,
                    reason="Next.js import detected",
                    confidence=0.95,
                    type=EvidenceType.EXPLICIT_IMPORT,
                )
            )
    
    def _add_technology(
        self,
        name: str,
        category: str,
        confidence: float,
        evidence: Evidence,
        version: str = None,
    ):
        """Add or update detected technology"""
        key = name.lower()
        
        if key in self.detected:
            # Update existing
            tech = self.detected[key]
            tech.evidence.append(evidence)
            tech.confidence = max(tech.confidence, confidence)
            if version and not tech.version:
                tech.version = version
        else:
            # Add new
            self.detected[key] = DetectedTechnology(
                name=name,
                version=version,
                confidence=confidence,
                evidence=[evidence],
            )
    
    def _build_stack_summary(self) -> StackSummary:
        """Build final stack summary"""
        stack = StackSummary()
        
        # Categorize technologies
        for tech in self.detected.values():
            # Determine category
            if tech.name.lower() in ["python", "typescript", "javascript", "go", "rust"]:
                stack.languages.append(tech)
            elif tech.name.lower() in ["fastapi", "flask", "django", "express", "nestjs"]:
                stack.backend.append(tech)
            elif tech.name.lower() in ["react", "vue", "next.js", "vite"]:
                stack.frontend.append(tech)
            elif tech.name.lower() in ["postgresql", "mysql", "mongodb", "sqlalchemy"]:
                stack.database.append(tech)
            elif tech.name.lower() in ["redis", "memcached"]:
                stack.cache.append(tech)
            elif tech.name.lower() in ["celery", "bullmq"]:
                stack.workers.append(tech)
            elif tech.name.lower() in ["stripe", "twilio", "sendgrid"]:
                # External services
                pass
            elif tech.name.lower() in ["pytest", "jest", "vitest"]:
                stack.testing.append(tech)
        
        # Calculate overall confidence
        if self.detected:
            stack.overall_confidence = sum(t.confidence for t in self.detected.values()) / len(self.detected)
        
        return stack
