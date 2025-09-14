### Embedding in Bert 
Embeddings are dense numerical vectors that represent words or pieces of words (tokens) in a way that a machine learning model can understand. These vectors are designed to capture the **semantic** meaning and **contextual** relationships of the text.


#### Semantic
Semantic search is an advanced data searching technique that goes beyond simply matching keywords. Instead, it focuses on understanding the contextual meaning and intent behind a user's search query, just like a human would.


#### Normalize Embedding
To normalize an embedding means to scale its numerical vector so that its length (or magnitude) becomes equal to 1. This process is crucial in many machine learning applications because it ensures that similarity comparisons between embeddings are based purely on their direction rather than their magnitude.

To normalize an embedding means to scale its numerical vector so that its length (or magnitude) becomes equal to 1. This process is crucial in many machine learning applications because it ensures that similarity comparisons between embeddings are based purely on their direction rather than their magnitude.

In simple terms, imagine embeddings as arrows pointing in different directions in a multi-dimensional space. The length of the arrow might not always be meaningful. Normalizing these embeddings is like making every single arrow have the exact same length, so the only thing that matters when comparing them is the angle between them.

#### L2 Normalization
L2 normalization is the most common method for normalizing embeddings. It is also known as Euclidean normalization or unit vector scaling.

The process for L2 normalization is as follows:

1. Calculate the L2 norm (length) of the vector. This is done by taking the square root of the sum of the squares of all the vector's components.
2. Divide each component of the original vector by this calculated L2 norm. This scales the vector to a length of 1, placing it on a "unit sphere."

##### Why is it useful?
L2 normalization is particularly important for tasks involving cosine similarity. Cosine similarity measures the cosine of the angle between two vectors and is a popular metric for determining how semantically similar two embeddings are. When embeddings are L2 normalized, calculating their cosine similarity is mathematically equivalent to a simple dot product, which is computationally much faster. This makes L2 normalization a key preprocessing step for tasks like semantic search and recommendation systems.