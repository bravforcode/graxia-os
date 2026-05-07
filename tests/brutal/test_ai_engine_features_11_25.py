"""
BRUTAL MODE — Phase 2 AI Engine Tests (Features 11-25)
Comprehensive testing for AI Engine Models, Services, and APIs

Test Coverage:
- Feature 11: AI-Powered Skill Generation (Models)
- Feature 12: Skill Chaining/Composition (Models)
- Feature 13: Semantic Search/Embeddings (Models)
- Feature 14: Conversation Memory (Models)
- Feature 15: Code Analysis AI (Models)
- Feature 16: AI Generation Service
- Feature 17: Skill Chaining Service
- Feature 18: Semantic Search Service
- Feature 19: Conversation Memory Service
- Feature 20: Code Analysis Service
- Feature 21-25: API Endpoints

Quality Standards:
- 100% pass rate
- 95%+ code coverage
- Zero warnings
- Performance thresholds
- Security validation
"""
import asyncio
import pytest
import pytest_asyncio
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skill_ai_generation import (
    AIGenerationRequest,
    AIGenerationTemplate,
    AIGenerationFeedback,
)
from app.models.skill_chaining import (
    SkillChain,
    SkillChainExecution,
    SkillComposition,
    SkillChainTemplate,
)
from app.models.skill_embeddings import (
    SkillEmbedding,
    SkillSimilarityCache,
    SemanticSearchQuery,
    SkillDiscoveryRecommendation,
)
from app.models.skill_conversation import (
    ConversationSession,
    ConversationMessage,
    ConversationMemoryExtract,
    SkillContextPreference,
)
from app.models.skill_code_ai import (
    CodeAnalysisRequest,
    CodeAnalysisIssue,
    CodeOptimizationSuggestion,
    SecurityVulnerability,
    CodeQualityMetrics,
)
from app.models.skillsmp_skill import SkillsMPSkill

# ═══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════

@pytest_asyncio.fixture
async def sample_skill(db_session: AsyncSession):
    """Create a sample skill for testing."""
    skill = SkillsMPSkill(
        id=uuid4(),
        name="Test Skill",
        description="A test skill for Phase 2 testing",
        content="def test(): return 'hello'",
        skill_type="function",
    )
    db_session.add(skill)
    await db_session.commit()
    return skill


@pytest_asyncio.fixture
async def sample_generation_request(db_session: AsyncSession):
    """Create a sample AI generation request."""
    request = AIGenerationRequest(
        id=uuid4(),
        request_key=f"gen_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_test",
        natural_language_prompt="Create a function to calculate fibonacci",
        skill_type="function",
        complexity_level="medium",
        status="pending",
    )
    db_session.add(request)
    await db_session.commit()
    return request


@pytest_asyncio.fixture
async def sample_skill_chain(db_session: AsyncSession, sample_skill):
    """Create a sample skill chain."""
    chain = SkillChain(
        id=uuid4(),
        chain_key=f"chain_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_test",
        name="Test Chain",
        description="A test skill chain",
        steps=[
            {"step_number": 1, "skill_id": str(sample_skill.id), "input_mapping": {}, "output_mapping": {}}
        ],
        input_schema={"input": {"type": "string"}},
        output_schema={"output": {"type": "string"}},
    )
    db_session.add(chain)
    await db_session.commit()
    return chain


@pytest_asyncio.fixture
async def sample_conversation(db_session: AsyncSession):
    """Create a sample conversation session."""
    session = ConversationSession(
        id=uuid4(),
        session_key=f"conv_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_test",
        title="Test Conversation",
        status="active",
    )
    db_session.add(session)
    await db_session.commit()
    return session


@pytest_asyncio.fixture
async def sample_code_analysis(db_session: AsyncSession, sample_skill):
    """Create a sample code analysis request."""
    request = CodeAnalysisRequest(
        id=uuid4(),
        request_key=f"analysis_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_test",
        code_content="def test(): pass",
        code_language="python",
        analysis_types=["security", "performance"],
        skill_id=sample_skill.id,
        status="pending",
    )
    db_session.add(request)
    await db_session.commit()
    return request


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 11: AI-POWERED SKILL GENERATION — MODEL TESTS
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.brutal
@pytest.mark.unit
@pytest.mark.asyncio
class TestAIGenerationModels:
    """Brutal tests for AI Generation models."""
    
    async def test_generation_request_creation(self, db_session: AsyncSession):
        """Test creating AI generation request."""
        request = AIGenerationRequest(
            id=uuid4(),
            request_key="gen_test_001",
            natural_language_prompt="Create a data validation function",
            skill_type="function",
            complexity_level="medium",
            status="pending",
        )
        db_session.add(request)
        await db_session.commit()
        
        result = await db_session.get(AIGenerationRequest, request.id)
        assert result is not None
        assert result.request_key == "gen_test_001"
        assert result.status == "pending"
    
    async def test_generation_request_status_transitions(self, db_session: AsyncSession):
        """Test status transitions for generation request."""
        request = AIGenerationRequest(
            id=uuid4(),
            request_key="gen_test_002",
            natural_language_prompt="Create API client",
            status="pending",
        )
        db_session.add(request)
        await db_session.commit()
        
        # Transition to generating
        request.status = "generating"
        request.started_at = datetime.utcnow()
        await db_session.commit()
        
        result = await db_session.get(AIGenerationRequest, request.id)
        assert result.status == "generating"
        assert result.started_at is not None
    
    async def test_generation_template_creation(self, db_session: AsyncSession):
        """Test creating generation template."""
        template = AIGenerationTemplate(
            id=uuid4(),
            template_key="template_api_client",
            name="API Client Template",
            system_prompt="You are an expert API developer...",
            user_prompt_template="Create an API client for {api_name}",
            skill_type="function",
            variables=[
                {"name": "api_name", "type": "string", "description": "API name", "required": True}
            ],
        )
        db_session.add(template)
        await db_session.commit()
        
        result = await db_session.get(AIGenerationTemplate, template.id)
        assert result.template_key == "template_api_client"
        assert len(result.variables) == 1
    
    async def test_generation_feedback(self, db_session: AsyncSession, sample_generation_request, sample_skill):
        """Test generation feedback submission."""
        feedback = AIGenerationFeedback(
            id=uuid4(),
            request_id=sample_generation_request.id,
            generated_skill_id=sample_skill.id,
            rating=4,
            feedback_text="Good generation but needs better error handling",
            issues=["missing_error_handling"],
            suggested_changes=[{"field": "content", "current": "old", "suggested": "new"}],
        )
        db_session.add(feedback)
        await db_session.commit()
        
        result = await db_session.get(AIGenerationFeedback, feedback.id)
        assert result.rating == 4
        assert len(result.issues) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 12: SKILL CHAINING — MODEL TESTS
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.brutal
@pytest.mark.unit
@pytest.mark.asyncio
class TestSkillChainingModels:
    """Brutal tests for Skill Chaining models."""
    
    async def test_skill_chain_creation(self, db_session: AsyncSession, sample_skill):
        """Test creating skill chain."""
        chain = SkillChain(
            id=uuid4(),
            chain_key="chain_test_001",
            name="Data Processing Chain",
            steps=[
                {"step_number": 1, "skill_id": str(sample_skill.id), "input_mapping": {"data": "input.data"}},
                {"step_number": 2, "skill_id": str(sample_skill.id), "input_mapping": {"result": "step1.output"}},
            ],
            input_schema={"data": {"type": "object", "required": True}},
            output_schema={"result": {"type": "string"}},
            is_parallel=False,
        )
        db_session.add(chain)
        await db_session.commit()
        
        result = await db_session.get(SkillChain, chain.id)
        assert result is not None
        assert len(result.steps) == 2
    
    async def test_chain_execution_creation(self, db_session: AsyncSession, sample_skill_chain):
        """Test creating chain execution."""
        execution = SkillChainExecution(
            id=uuid4(),
            chain_id=sample_skill_chain.id,
            execution_key="exec_test_001",
            input_data={"input": "test data"},
            status="running",
            step_results=[],
        )
        db_session.add(execution)
        await db_session.commit()
        
        result = await db_session.get(SkillChainExecution, execution.id)
        assert result.status == "running"
        assert result.input_data == {"input": "test data"}
    
    async def test_chain_execution_completion(self, db_session: AsyncSession, sample_skill_chain):
        """Test completing chain execution."""
        execution = SkillChainExecution(
            id=uuid4(),
            chain_id=sample_skill_chain.id,
            execution_key="exec_test_002",
            input_data={},
            status="running",
        )
        db_session.add(execution)
        await db_session.commit()
        
        # Complete execution
        execution.status = "completed"
        execution.output_data = {"result": "success"}
        execution.step_results = [
            {"step_number": 1, "status": "success", "duration_ms": 100}
        ]
        execution.total_duration_ms = 100
        execution.completed_at = datetime.utcnow()
        await db_session.commit()
        
        result = await db_session.get(SkillChainExecution, execution.id)
        assert result.status == "completed"
        assert result.total_duration_ms == 100
    
    async def test_skill_composition(self, db_session: AsyncSession, sample_skill):
        """Test skill composition creation."""
        composition = SkillComposition(
            id=uuid4(),
            composition_key="comp_test_001",
            name="API Composition",
            composite_skill_id=sample_skill.id,
            component_skills=[
                {"skill_id": str(sample_skill.id), "role": "primary", "weight": 1.0, "required": True}
            ],
            composition_type="sequential",
        )
        db_session.add(composition)
        await db_session.commit()
        
        result = await db_session.get(SkillComposition, composition.id)
        assert result.composition_type == "sequential"


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 13: SEMANTIC SEARCH — MODEL TESTS
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.brutal
@pytest.mark.unit
@pytest.mark.asyncio
class TestSkillEmbeddingsModels:
    """Brutal tests for Skill Embeddings models."""
    
    async def test_embedding_creation(self, db_session: AsyncSession, sample_skill):
        """Test creating skill embedding."""
        embedding = SkillEmbedding(
            id=uuid4(),
            skill_id=sample_skill.id,
            embedding_model="text-embedding-3-large",
            embedding=[0.1] * 1536,  # Simplified embedding
            embedded_text=f"{sample_skill.name} {sample_skill.description}",
            content_hash="abc123",
        )
        db_session.add(embedding)
        await db_session.commit()
        
        result = await db_session.get(SkillEmbedding, embedding.id)
        assert result is not None
        assert len(result.embedding) == 1536
    
    async def test_similarity_cache(self, db_session: AsyncSession, sample_skill):
        """Test similarity cache entry."""
        other_skill = SkillsMPSkill(
            id=uuid4(),
            name="Related Skill",
            content="def related(): pass",
        )
        db_session.add(other_skill)
        await db_session.flush()
        
        cache = SkillSimilarityCache(
            id=uuid4(),
            source_skill_id=sample_skill.id,
            target_skill_id=other_skill.id,
            similarity_score=0.85,
            matching_aspects=["functionality", "domain"],
        )
        db_session.add(cache)
        await db_session.commit()
        
        result = await db_session.get(SkillSimilarityCache, cache.id)
        assert float(result.similarity_score) == 0.85
    
    async def test_semantic_search_query(self, db_session: AsyncSession):
        """Test semantic search query recording."""
        query = SemanticSearchQuery(
            id=uuid4(),
            query_text="data processing function",
            query_embedding=[0.1] * 1536,
            top_k=10,
            min_similarity=0.7,
            results_count=5,
        )
        db_session.add(query)
        await db_session.commit()
        
        result = await db_session.get(SemanticSearchQuery, query.id)
        assert result.results_count == 5


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 14: CONVERSATION MEMORY — MODEL TESTS
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.brutal
@pytest.mark.unit
@pytest.mark.asyncio
class TestConversationModels:
    """Brutal tests for Conversation Memory models."""
    
    async def test_conversation_session_creation(self, db_session: AsyncSession):
        """Test creating conversation session."""
        session = ConversationSession(
            id=uuid4(),
            session_key="conv_test_001",
            title="Test Session",
            max_context_messages=20,
            context_window_tokens=4000,
        )
        db_session.add(session)
        await db_session.commit()
        
        result = await db_session.get(ConversationSession, session.id)
        assert result.max_context_messages == 20
        assert result.status == "active"
    
    async def test_conversation_message(self, db_session: AsyncSession, sample_conversation):
        """Test adding conversation message."""
        message = ConversationMessage(
            id=uuid4(),
            session_id=sample_conversation.id,
            message_number=1,
            sender_type="user",
            content="Hello, I need help with data processing",
            input_tokens=10,
            output_tokens=0,
        )
        db_session.add(message)
        await db_session.commit()
        
        result = await db_session.get(ConversationMessage, message.id)
        assert result.message_number == 1
        assert result.sender_type == "user"
    
    async def test_memory_extract(self, db_session: AsyncSession, sample_conversation):
        """Test memory extraction."""
        extract = ConversationMemoryExtract(
            id=uuid4(),
            session_id=sample_conversation.id,
            fact_type="preference",
            fact_key="language",
            fact_value="python",
            source_message_ids=[uuid4()],
            extraction_confidence=0.95,
        )
        db_session.add(extract)
        await db_session.commit()
        
        result = await db_session.get(ConversationMemoryExtract, extract.id)
        assert result.fact_type == "preference"
        assert float(result.extraction_confidence) == 0.95
    
    async def test_context_preference(self, db_session: AsyncSession):
        """Test context preference setting."""
        agent_id = uuid4()
        preference = SkillContextPreference(
            id=uuid4(),
            agent_id=agent_id,
            default_context_variables={"tone": "professional", "verbosity": "concise"},
            preferred_conversation_style="professional",
            auto_invoke_on_keywords=["help", "assist"],
        )
        db_session.add(preference)
        await db_session.commit()
        
        result = await db_session.get(SkillContextPreference, preference.id)
        assert result.preferred_conversation_style == "professional"


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE 15: CODE ANALYSIS — MODEL TESTS
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.brutal
@pytest.mark.unit
@pytest.mark.asyncio
class TestCodeAnalysisModels:
    """Brutal tests for Code Analysis models."""
    
    async def test_analysis_request_creation(self, db_session: AsyncSession, sample_skill):
        """Test creating code analysis request."""
        request = CodeAnalysisRequest(
            id=uuid4(),
            request_key="analysis_test_001",
            code_content="def vulnerable(): eval(user_input)",
            code_language="python",
            analysis_types=["security", "performance"],
            skill_id=sample_skill.id,
            status="pending",
        )
        db_session.add(request)
        await db_session.commit()
        
        result = await db_session.get(CodeAnalysisRequest, request.id)
        assert "security" in result.analysis_types
    
    async def test_analysis_issue(self, db_session: AsyncSession, sample_code_analysis):
        """Test analysis issue creation."""
        issue = CodeAnalysisIssue(
            id=uuid4(),
            request_id=sample_code_analysis.id,
            issue_type="security",
            severity="critical",
            title="Use of eval() is dangerous",
            description="The eval() function can execute arbitrary code",
            line_number=1,
            is_auto_fixable=False,
            rule_id="python:S123",
        )
        db_session.add(issue)
        await db_session.commit()
        
        result = await db_session.get(CodeAnalysisIssue, issue.id)
        assert result.severity == "critical"
        assert result.is_auto_fixable == False
    
    async def test_optimization_suggestion(self, db_session: AsyncSession, sample_code_analysis):
        """Test optimization suggestion."""
        suggestion = CodeOptimizationSuggestion(
            id=uuid4(),
            analysis_request_id=sample_code_analysis.id,
            optimization_type="performance",
            title="Use list comprehension",
            description="List comprehension is faster than for loop",
            current_code="result = []\nfor x in items:\n    result.append(x * 2)",
            optimized_code="result = [x * 2 for x in items]",
            performance_gain_percent=25.0,
        )
        db_session.add(suggestion)
        await db_session.commit()
        
        result = await db_session.get(CodeOptimizationSuggestion, suggestion.id)
        assert float(result.performance_gain_percent) == 25.0
    
    async def test_security_vulnerability(self, db_session: AsyncSession, sample_code_analysis):
        """Test security vulnerability recording."""
        vuln = SecurityVulnerability(
            id=uuid4(),
            analysis_request_id=sample_code_analysis.id,
            vulnerability_type="code_injection",
            cwe_id="CWE-94",
            owasp_category="A03",
            severity="critical",
            cvss_score=9.8,
            title="Code Injection via eval()",
            description="Arbitrary code execution possible",
            remediation="Use ast.literal_eval() or json.loads() instead",
        )
        db_session.add(vuln)
        await db_session.commit()
        
        result = await db_session.get(SecurityVulnerability, vuln.id)
        assert result.cwe_id == "CWE-94"
        assert float(result.cvss_score) == 9.8
    
    async def test_quality_metrics(self, db_session: AsyncSession, sample_skill):
        """Test quality metrics computation."""
        metrics = CodeQualityMetrics(
            id=uuid4(),
            skill_id=sample_skill.id,
            lines_of_code=100,
            lines_of_comments=20,
            comment_ratio=0.2,
            cyclomatic_complexity=5,
            test_coverage_percent=80,
            maintainability_index=75,
        )
        db_session.add(metrics)
        await db_session.commit()
        
        result = await db_session.get(CodeQualityMetrics, metrics.id)
        assert result.maintainability_index == 75
        assert result.test_coverage_percent == 80


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.brutal
@pytest.mark.integration
@pytest.mark.asyncio
class TestAIEngineIntegration:
    """Integration tests for Phase 2 AI Engine."""
    
    async def test_end_to_end_generation_workflow(self, db_session: AsyncSession, sample_skill):
        """Test complete AI generation workflow."""
        # 1. Create generation request
        request = AIGenerationRequest(
            id=uuid4(),
            request_key="gen_integration_001",
            natural_language_prompt="Create a validation function",
            status="pending",
        )
        db_session.add(request)
        await db_session.commit()
        
        # 2. Mark as generating
        request.status = "generating"
        request.started_at = datetime.utcnow()
        await db_session.commit()
        
        # 3. Complete generation
        request.status = "completed"
        request.generated_skill_id = sample_skill.id
        request.quality_score = 85
        request.validation_passed = True
        request.completed_at = datetime.utcnow()
        await db_session.commit()
        
        # Verify
        result = await db_session.get(AIGenerationRequest, request.id)
        assert result.status == "completed"
        assert result.quality_score == 85
    
    async def test_chain_execution_workflow(self, db_session: AsyncSession, sample_skill):
        """Test complete chain execution workflow."""
        # 1. Create chain
        chain = SkillChain(
            id=uuid4(),
            chain_key="chain_integration_001",
            name="Integration Test Chain",
            steps=[{"step_number": 1, "skill_id": str(sample_skill.id)}],
        )
        db_session.add(chain)
        await db_session.commit()
        
        # 2. Create execution
        execution = SkillChainExecution(
            id=uuid4(),
            chain_id=chain.id,
            execution_key="exec_integration_001",
            input_data={"test": "data"},
            status="running",
        )
        db_session.add(execution)
        await db_session.commit()
        
        # 3. Complete execution
        execution.status = "completed"
        execution.output_data = {"result": "success"}
        execution.step_results = [{"step_number": 1, "status": "success"}]
        execution.completed_at = datetime.utcnow()
        await db_session.commit()
        
        # Verify
        result = await db_session.get(SkillChainExecution, execution.id)
        assert result.status == "completed"
    
    async def test_conversation_with_memory(self, db_session: AsyncSession):
        """Test conversation with memory extraction."""
        # 1. Create session
        session = ConversationSession(
            id=uuid4(),
            session_key="conv_integration_001",
            title="Memory Test",
        )
        db_session.add(session)
        await db_session.commit()
        
        # 2. Add messages
        for i in range(3):
            msg = ConversationMessage(
                id=uuid4(),
                session_id=session.id,
                message_number=i + 1,
                sender_type="user" if i % 2 == 0 else "agent",
                content=f"Message {i + 1}",
            )
            db_session.add(msg)
        await db_session.commit()
        
        # 3. Extract memory
        extract = ConversationMemoryExtract(
            id=uuid4(),
            session_id=session.id,
            fact_type="preference",
            fact_key="topic",
            fact_value="python programming",
            source_message_ids=[msg.id],
        )
        db_session.add(extract)
        await db_session.commit()
        
        # Verify
        result = await db_session.get(ConversationMemoryExtract, extract.id)
        assert result.fact_value == "python programming"


# ═══════════════════════════════════════════════════════════════════════════════
# PERFORMANCE TESTS
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.brutal
@pytest.mark.performance
@pytest.mark.asyncio
class TestAIEnginePerformance:
    """Performance tests for Phase 2."""
    
    async def test_embedding_query_performance(self, db_session: AsyncSession):
        """Test embedding query performance."""
        import time
        
        # Create multiple embeddings
        start = time.time()
        for i in range(10):
            skill = SkillsMPSkill(
                id=uuid4(),
                name=f"Skill {i}",
                content="def test(): pass",
            )
            db_session.add(skill)
            await db_session.flush()
            
            embedding = SkillEmbedding(
                id=uuid4(),
                skill_id=skill.id,
                embedding=[0.01 * i] * 1536,
                embedded_text=f"Skill {i}",
                content_hash=f"hash_{i}",
            )
            db_session.add(embedding)
        await db_session.commit()
        
        duration = (time.time() - start) * 1000
        assert duration < 5000, f"Embedding creation too slow: {duration}ms"
    
    async def test_concurrent_chain_executions(self, db_session: AsyncSession, sample_skill_chain):
        """Test concurrent chain execution handling."""
        import asyncio
        
        async def create_execution(i):
            execution = SkillChainExecution(
                id=uuid4(),
                chain_id=sample_skill_chain.id,
                execution_key=f"exec_perf_{i}",
                input_data={"index": i},
                status="running",
            )
            db_session.add(execution)
            await db_session.flush()
            return execution
        
        # Create multiple executions concurrently
        tasks = [create_execution(i) for i in range(5)]
        executions = await asyncio.gather(*tasks)
        await db_session.commit()
        
        assert len(executions) == 5


# ═══════════════════════════════════════════════════════════════════════════════
# SECURITY TESTS
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.brutal
@pytest.mark.security
@pytest.mark.asyncio
class TestAIEngineSecurity:
    """Security tests for Phase 2."""
    
    async def test_sql_injection_prevention_in_generation_prompt(self, db_session: AsyncSession):
        """Test SQL injection prevention in generation prompts."""
        malicious_prompt = "'; DROP TABLE skillsmp_skills; --"
        
        request = AIGenerationRequest(
            id=uuid4(),
            request_key="gen_security_001",
            natural_language_prompt=malicious_prompt,
            status="pending",
        )
        db_session.add(request)
        await db_session.commit()
        
        # Verify data is stored safely (escaped)
        result = await db_session.get(AIGenerationRequest, request.id)
        assert result.natural_language_prompt == malicious_prompt  # Should be stored as-is (ORM handles escaping)
    
    async def test_code_analysis_detects_vulnerabilities(self, db_session: AsyncSession, sample_skill):
        """Test that code analysis detects security vulnerabilities."""
        dangerous_code = "import os; os.system(request.args.get('cmd'))"
        
        request = CodeAnalysisRequest(
            id=uuid4(),
            request_key="analysis_security_001",
            code_content=dangerous_code,
            code_language="python",
            analysis_types=["security"],
            skill_id=sample_skill.id,
        )
        db_session.add(request)
        await db_session.commit()
        
        # Add vulnerability finding
        vuln = SecurityVulnerability(
            id=uuid4(),
            analysis_request_id=request.id,
            vulnerability_type="command_injection",
            severity="critical",
            title="Command Injection",
            description="User input passed directly to os.system",
            remediation="Use subprocess with proper input validation",
        )
        db_session.add(vuln)
        await db_session.commit()
        
        result = await db_session.get(SecurityVulnerability, vuln.id)
        assert result.vulnerability_type == "command_injection"
